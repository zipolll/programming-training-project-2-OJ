"""Course-compatible authentication paths."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.app.core.responses import ApiResponse
from backend.app.core.routing import CourseRoute
from backend.app.modules.users.dependencies import get_auth_service, require_login
from backend.app.modules.users.models import Credentials, User
from backend.app.modules.users.service import (
    AuthService,
    BannedUserError,
    InvalidCredentialsError,
)

router = APIRouter(route_class=CourseRoute)
BRIDGE_COOKIE_PATH = "/api/auth/bridge"
BRIDGE_CSRF_HEADER = "X-OJ-Bridge"


class BridgeToken(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class BridgeTicket(BaseModel):
    ticket: str = Field(min_length=32, max_length=256)


def _require_browser_bridge_request(request: Request, auth_service: AuthService) -> None:
    origin = request.headers.get("origin")
    if origin not in auth_service.settings.cors_origins:
        raise HTTPException(status_code=403, detail="Invalid browser origin")
    if request.headers.get(BRIDGE_CSRF_HEADER) != "1":
        raise HTTPException(status_code=403, detail="Invalid bridge request")


def _set_session_cookie(
    response: Response,
    auth_service: AuthService,
    session_id: str,
    expires_at: datetime,
) -> None:
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


def _delete_bridge_cookie(response: Response, auth_service: AuthService) -> None:
    response.delete_cookie(
        key=auth_service.settings.session_bridge_cookie_name,
        path=BRIDGE_COOKIE_PATH,
        secure=auth_service.settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


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
    _set_session_cookie(response, auth_service, session_id, expires_at)
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


@router.post("/bridge/issue", response_model=ApiResponse)
async def issue_bridge(
    request: Request,
    current_user: Annotated[User, Depends(require_login)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse:
    """Create an unclaimed browser recovery token for the current login."""
    session_id = request.cookies[auth_service.settings.session_cookie_name]
    token = await auth_service.issue_bridge(session_id, current_user.id)
    return ApiResponse(msg="bridge issued", data={"token": token})


@router.post("/bridge/claim", response_model=ApiResponse)
async def claim_bridge(
    payload: BridgeToken,
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse:
    """Move a one-use claim token into an HttpOnly browser cookie."""
    _require_browser_bridge_request(request, auth_service)
    if not await auth_service.claim_bridge(payload.token):
        _delete_bridge_cookie(response, auth_service)
        raise HTTPException(status_code=401, detail="Invalid recovery token")
    response.set_cookie(
        key=auth_service.settings.session_bridge_cookie_name,
        value=payload.token,
        max_age=auth_service.settings.session_bridge_max_age_seconds,
        path=BRIDGE_COOKIE_PATH,
        secure=auth_service.settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return ApiResponse(msg="bridge claimed")


@router.post("/bridge/ticket", response_model=ApiResponse)
async def create_bridge_ticket(
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse:
    """Issue a short-lived one-use ticket to an authenticated browser."""
    _require_browser_bridge_request(request, auth_service)
    bridge_token = request.cookies.get(auth_service.settings.session_bridge_cookie_name)
    if not bridge_token:
        raise HTTPException(status_code=401, detail="No recovery session")
    ticket = await auth_service.issue_bridge_ticket(bridge_token)
    if ticket is None:
        _delete_bridge_cookie(response, auth_service)
        raise HTTPException(status_code=401, detail="Recovery session expired")
    return ApiResponse(msg="ticket issued", data={"ticket": ticket})


@router.post("/bridge/exchange", response_model=ApiResponse)
async def exchange_bridge_ticket(
    payload: BridgeTicket,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse:
    """Exchange a one-use browser ticket for a server-side API session."""
    exchanged = await auth_service.exchange_bridge_ticket(payload.ticket)
    if exchanged is None:
        raise HTTPException(status_code=401, detail="Invalid recovery ticket")
    session_id, expires_at = exchanged
    _set_session_cookie(response, auth_service, session_id, expires_at)
    return ApiResponse(msg="session restored")


@router.post("/bridge/clear", response_model=ApiResponse)
async def clear_bridge(
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse:
    """Revoke and remove the browser recovery cookie."""
    _require_browser_bridge_request(request, auth_service)
    bridge_token = request.cookies.get(auth_service.settings.session_bridge_cookie_name)
    if bridge_token:
        await auth_service.revoke_bridge(bridge_token)
    _delete_bridge_cookie(response, auth_service)
    return ApiResponse(msg="bridge cleared")
