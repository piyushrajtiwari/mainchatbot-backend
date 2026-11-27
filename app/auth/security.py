from datetime import datetime, timedelta, timezone
import hashlib
from jose import JWTError, jwt
from typing import Optional 
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.model import EmailVerification,User,RefreshToken
from sqlalchemy import select,delete,update
import resend
from app.core.settings import settings
from app.core.template import email_template, password_reset_template
from urllib.parse import quote

from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
import secrets

password_hash = PasswordHash((BcryptHasher(),))

resend.api_key = settings.RESEND_API_KEY


def get_password_hash(password: str) -> str:
    """Hash a plain-text password before saving to User.hash_password."""
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text login password against the stored hash."""
    return password_hash.verify(plain_password, hashed_password)


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(
    data: dict, expires_minutes: Optional[int] = None
) -> str:
    to_encode = data.copy()

    # Use custom minutes if provided; otherwise fallback to .env setting
    minutes = (
        expires_minutes
        if expires_minutes is not None
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

async def token(session: AsyncSession, user: User) -> dict:
   
    access_token = create_access_token(
        data={"sub": str(user.id)}
    )

    refresh_token = secrets.token_urlsafe(64)
    refresh_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    expired_at = datetime.now(timezone.utc) + timedelta(days=refresh_days)

   
    new_refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expired_at=expired_at,
    )
    session.add(new_refresh_token)
    await session.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }



# 2. Verify and decode a JWT token
async def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


async def rotate_refresh_token(session: AsyncSession, refresh_token: str) -> dict:
    """Consume a refresh token once and issue a replacement token pair."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token == refresh_token,
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expired_at > now,
        )
        .values(is_revoked=True, revoked_at=now)
        .returning(RefreshToken.user_id, RefreshToken.id)
    )
    consumed = result.one_or_none()
    if consumed is None:
        await session.rollback()
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await session.get(User, consumed.user_id)
    if user is None or user.deleted_at is not None:
        await session.rollback()
        raise HTTPException(status_code=401, detail="User not found")

    new_refresh_token = secrets.token_urlsafe(64)
    session.add(
        RefreshToken(
            user_id=user.id,
            token=new_refresh_token,
            expired_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            revoked_from_id=consumed.id,
        )
    )
    access_token = create_access_token({"sub": str(user.id)})
    await session.commit()
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }

def send_resend_email_task(email: str, name: str, token: str) -> None:
    verification_base = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email" if settings.FRONTEND_URL else f"{settings.BACKEND_URL.rstrip('/')}/auth/verify-email"
    verification_link = f"{verification_base}?token={token}"
    html_content = email_template(email, name, verification_link)

    params: resend.Emails.SendParams = {
        "from": settings.FROM_EMAIL,
        "to": [email],
        "subject": "Verify your email address",
        "html": html_content,
    }
    resend.Emails.send(params) 


def send_password_reset_email_task(email: str, name: str, token: str) -> None:
    reset_base = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password" if settings.FRONTEND_URL else f"{settings.BACKEND_URL.rstrip('/')}/auth/reset-password"
    reset_link = f"{reset_base}?token={quote(token, safe='')}"
    params: resend.Emails.SendParams = {
        "from": settings.FROM_EMAIL,
        "to": [email],
        "subject": "Reset your password",
        "html": password_reset_template(email, name, reset_link),
    }
    resend.Emails.send(params)

async def prepare_verification_token(session: AsyncSession, email: str) -> tuple[str, str]:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = existing_user.id

    stmt1 = select(EmailVerification).where(EmailVerification.user_id == user_id)
    result1 = await session.execute(stmt1)
    existing_verification = result1.scalar_one_or_none()

    # FIX 1: expired_at ko 'if existing_verification:' ke ANDAR rakha hai
    if existing_verification:
        if existing_verification.status == "accepted":
            raise HTTPException(status_code=400, detail="Email is already verified")

        expired_at = existing_verification.expired_at
        if expired_at.tzinfo is None:
            expired_at = expired_at.replace(tzinfo=timezone.utc)

        if (datetime.now(timezone.utc) > expired_at) or (existing_verification.status == "pending"):
            stmt3 = delete(EmailVerification).where(EmailVerification.user_id == user_id)
            await session.execute(stmt3)
            await session.commit()

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    new_verification = EmailVerification(
        user_id=user_id,
        token=token,
        status="pending",
        expired_at=expires_at,
    )
    session.add(new_verification)
    await session.commit()

    return existing_user.name, token 

async def email_send(session: AsyncSession, email: str) -> dict:
    name, token = await prepare_verification_token(session, email)

    try:
        send_resend_email_task(email, name, token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

    return {"message": "Verification email sent successfully"}


    

    
            
    
