"""Reusable authentication and authorization dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from backend.app.modules.users.models import User, UserRole
from backend.app.modules.users.service import AuthService


async def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


async def get_current_user(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User | None:
    session_id = request.cookies.get(auth_service.settings.session_cookie_name)
    if not session_id:
        return None
    return await auth_service.get_user_for_session(session_id)


async def require_login(
    current_user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return current_user


async def require_admin(
    current_user: Annotated[User, Depends(require_login)],
) -> User:
    if current_user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Permission denied")
    return current_user
