from urllib.parse import quote

from fastapi import APIRouter,status,Depends,BackgroundTasks,Response,Request,HTTPException,Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.settings import settings
from app.auth.schema import UserRegistrationIn,UserRegistrationOut,ForgotPasswordIn,ResetPasswordIn,ChangePasswordIn,MessageOut
from app.db.config import SessionDB
from app.auth.service import (
    Registration,
    email_verification as verify_email_service,
    user_login,
    refresh_user_token,
    forgot_password as forgot_password_service,
    reset_password as reset_password_service,
    change_password as change_password_service,
    logout_user,
)
from app.auth.dependancy import CurrentUser
from fastapi.security import OAuth2PasswordRequestForm
from app.core.cookies import set_auth_cookies, clear_auth_cookies
from typing import Annotated,Union

router = APIRouter(prefix="/auth",tags=["auth"])

@router.post("/user_registration",response_model=MessageOut,status_code=status.HTTP_201_CREATED)
async def user_registration(session:SessionDB,user:UserRegistrationIn,background_tasks: BackgroundTasks):
    
    users = await Registration(session,user,background_tasks)
   
    return users


@router.get("/verify-email")
async def email_verification(session:SessionDB,token:str) -> dict:
    
    return await verify_email_service(session,token) 



@router.post("/user_login")
async def login(response:Response,session:SessionDB,form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    
    result = await user_login(session,form_data.username,form_data.password)
    
    set_auth_cookies(
        response,
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
    )
    
    return {
        "access_token": result["access_token"],
        "token_type": result["token_type"],
    }
    

@router.post('/refresh')
async def refresh_token(request: Request, response: Response, session: SessionDB) -> dict:
    stored_token = request.cookies.get("refresh_token")
    if not stored_token:
        raise HTTPException(status_code=401, detail="Refresh token is required")

    result = await refresh_user_token(session, stored_token)
    set_auth_cookies(
        response,
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
    )
    return {
        "access_token": result["access_token"],
        "token_type": result["token_type"],
    }


@router.get("/me", response_model=UserRegistrationOut)
async def current_user(user: CurrentUser):
    return user

@router.post("/forgot-password")
async def forgot_password(
    session: SessionDB, data: ForgotPasswordIn, background_tasks: BackgroundTasks
) -> dict:
    return await forgot_password_service(session, data.email, background_tasks)


@router.get("/reset-password", include_in_schema=False)
async def reset_password_form(token: str = "") -> RedirectResponse:
    if not settings.FRONTEND_URL:
        raise HTTPException(status_code=503, detail="Password reset frontend is not configured")
    # Older emails still point here. Preserve their token and open the React page.
    response = RedirectResponse(
        f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={quote(token, safe='')}",
        status_code=303,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.post("/reset-password")
async def reset_password(
    request: Request,
    response: Response,
    session: SessionDB,
    data: Annotated[ResetPasswordIn, Form()],
):
    result = await reset_password_service(session, data.token, data.new_password)
    if "text/html" in request.headers.get("accept", ""):
        # Support older browser form submissions as well as the React JSON client.
        page = (RedirectResponse(f"{settings.FRONTEND_URL.rstrip('/')}/login", status_code=303)
                if settings.FRONTEND_URL else
                HTMLResponse("<h1>Password reset successfully</h1><p>You can sign in with your new password.</p>"))
        page.headers["Cache-Control"] = "no-store"
        clear_auth_cookies(page)
        return page
    clear_auth_cookies(response)
    return result


@router.post("/change-password")
async def change_password(
    response: Response, session: SessionDB, user: CurrentUser, data: ChangePasswordIn
) -> dict:
    result = await change_password_service(
        session, user, data.current_password, data.new_password
    )
    clear_auth_cookies(response)
    return result


@router.post("/logout")
async def logout(response: Response, session: SessionDB, user: CurrentUser) -> dict:
    result = await logout_user(session, user)
    clear_auth_cookies(response)
    return result
