from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from app.auth.model import User
from app.auth.service import get_current_user as get_current_user_service
from app.db.config import SessionDB


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/user_login", auto_error=False)


async def get_current_user(
    request: Request,
    session: SessionDB,
    bearer_token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    access_token = bearer_token or request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is required")
    return await get_current_user_service(session, access_token)


CurrentUser = Annotated[User, Depends(get_current_user)]
