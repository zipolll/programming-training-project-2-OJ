"""Course-compatible authentication paths."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.app.core.responses import ApiResponse
from backend.app.modules.users.dependencies import get_auth_service, require_login
from backend.app.modules.users.models import Credentials, User
from backend.app.modules.users.service import (
    AuthService,
    BannedUserError,
    InvalidCredentialsError,
)

router = APIRouter()


@router.post("/login", response_model=ApiResponse)
async def login(
    credentials: Credentials,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse:
    try:
        user, session_id, expires_at = await auth_service.login(
            credentials.username, credentials.password.get_secret_value()
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="Invalid username or password") from exc
    except BannedUserError as exc:
        raise HTTPException(status_code=403, detail="User is banned") from exc
    response.set_cookie(
        key=auth_service.settings.session_cookie_name,
        value=session_id,
        max_age=auth_service.settings.session_max_age_seconds,
        expires=expires_at,
        path="/",
        secure=auth_service.settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return ApiResponse(
        msg="login success",
        data={"user_id": str(user.id), "username": user.username, "role": user.role.value},
    )


@router.post("/logout", response_model=ApiResponse)
async def logout(
    request: Request,
    response: Response,
    current_user: Annotated[User, Depends(require_login)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse:
    del current_user
    session_id = request.cookies[auth_service.settings.session_cookie_name]
    await auth_service.logout(session_id)
    response.delete_cookie(
        key=auth_service.settings.session_cookie_name,
        path="/",
        secure=auth_service.settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return ApiResponse(msg="logout success")
