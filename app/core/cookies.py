from fastapi import Response
from app.core.settings import settings


def set_auth_cookies(
    response: Response|None = None,*, access_token: str, refresh_token: str
) -> None:
    # Localhost (HTTP) par secure=False, Production (HTTPS) par secure=True
    # is_production = getattr(settings, "ENVIRONMENT", "development") == "production"

    # 1. Access Token Cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,          # HTTPS only in production
        samesite="lax",                # CSRF protection ("none" agar frontend/backend alag domain par hon + HTTPS)
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Seconds mein
        path="/",
    )

    # 2. Refresh Token Cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 7 days in seconds
        path="/auth",                  # Security: Refresh cookie sirf /auth endpoints par hi bheji jayegi
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/auth")
