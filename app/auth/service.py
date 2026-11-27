from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.model import User, EmailVerification, PasswordResetToken, RefreshToken
from sqlalchemy import select, update
from datetime import datetime, timedelta, timezone
import secrets
from uuid import UUID
from fastapi import HTTPException,status,BackgroundTasks
from app.auth.security import (
    get_password_hash,
    prepare_verification_token,
    send_resend_email_task,
    verify_password,
    token,
    decode_access_token,
    rotate_refresh_token,
    hash_reset_token,
    send_password_reset_email_task,
    
)


async def Registration(session:AsyncSession,user,background_tasks: BackgroundTasks):
    
    stmt = select(User).where(user.email == User.email)
    result = await session.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )
    
    if (user.website or "").strip():
        return {"message": "Registration request received. Check your email for next steps."}
        
    
    new_user = User(
        name=user.name,
        email=user.email,
        hash_password=get_password_hash(user.password),
    )

    session.add(new_user)

    await session.commit()
    
    
    name, token = await prepare_verification_token(session, new_user.email)

    background_tasks.add_task(send_resend_email_task, new_user.email, name, token)
    
    return {
    "message": "Registration request received. Check your email for next steps."
}


    


async def email_verification(session:AsyncSession,token:str):
    
    stmt = select(EmailVerification).where(EmailVerification.token == token)
    result = await session.execute(stmt)
    token_check = result.scalar_one_or_none()

    # 2. Invalid token check
    if not token_check:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    
    if token_check.status == "accepted":
        return {"message": "Email is already verified"}

   
    expired_at = token_check.expired_at
    if expired_at.tzinfo is None:
        expired_at = expired_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expired_at:
        raise HTTPException(status_code=400, detail="Verification link has expired")
    
    user = await session.get(User, token_check.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    token_check.status = "accepted"
    user.is_verify = True
    await session.commit()

    return {"message": "Email verified successfully"}    

async def user_login(session:AsyncSession,email:str,password:str) -> dict:
        
    stmt = select(User).where(email == User.email)
    result = await session.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if not existing_user or not verify_password(password,existing_user.hash_password):
        raise HTTPException(
        status_code=401,
        detail="Invalid credentials"
    )
    if not existing_user.is_verify:
        raise HTTPException(
                status_code=400,
                detail="Verify your email ,check your email"
            )
        
    result = await token(session,existing_user)
    
    return result 


async def refresh_user_token(session: AsyncSession, refresh_token: str) -> dict:
    return await rotate_refresh_token(session, refresh_token)


async def get_current_user(session: AsyncSession, access_token: str) -> User:
    payload = await decode_access_token(access_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid access token")

    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def forgot_password(session: AsyncSession, email: str, background_tasks: BackgroundTasks) -> dict:
    message = {"message": "If an account exists for this email, a password reset link has been sent."}
    result = await session.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return message

    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(32)
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(raw_token),
            expired_at=now + timedelta(minutes=15),
        )
    )
    await session.commit()
    background_tasks.add_task(send_password_reset_email_task, user.email, user.name, raw_token)
    return message


async def reset_password(session: AsyncSession, raw_token: str, new_password: str) -> dict:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_reset_token(raw_token))
        .with_for_update()
    )
    reset_token = result.scalar_one_or_none()
    if reset_token is None or reset_token.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    expired_at = reset_token.expired_at
    if expired_at.tzinfo is None:
        expired_at = expired_at.replace(tzinfo=timezone.utc)
    if now >= expired_at:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user = await session.get(User, reset_token.user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hash_password = get_password_hash(new_password)
    reset_token.used_at = now
    await revoke_all_refresh_tokens(session, user.id, now)
    await session.commit()
    return {"message": "Password reset successfully. Please sign in again."}


async def revoke_all_refresh_tokens(session: AsyncSession, user_id: UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))
        .values(is_revoked=True, revoked_at=now)
    )


async def change_password(
    session: AsyncSession, current_user: User, current_password: str, new_password: str
) -> dict:
    result = await session.execute(
        select(User)
        .where(User.id == current_user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="User not found")
    if not verify_password(current_password, user.hash_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    now = datetime.now(timezone.utc)
    user.hash_password = get_password_hash(new_password)
    await revoke_all_refresh_tokens(session, user.id, now)
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    await session.commit()
    return {"message": "Password changed successfully. Please sign in again."}


async def logout_user(session: AsyncSession, current_user: User) -> dict:
    await revoke_all_refresh_tokens(session, current_user.id, datetime.now(timezone.utc))
    await session.commit()
    return {"message": "Logged out successfully"}
        
