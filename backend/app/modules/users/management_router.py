"""Course Step 4 user administration endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.core.responses import ApiResponse
from backend.app.core.routing import CourseRoute
from backend.app.modules.users.dependencies import get_auth_service, require_admin, require_login
from backend.app.modules.users.models import Credentials, RoleUpdateRequest, User
from backend.app.modules.users.service import (
    AuthService,
    LastAdministratorError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
    UserPermissionError,
    UserService,
    user_statistics_data,
)

router = APIRouter(route_class=CourseRoute)


async def get_user_service(request: Request) -> UserService:
    return request.app.state.user_service


@router.post("/", response_model=ApiResponse)
async def register(
    credentials: Credentials,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse:
    try:
        user = await auth_service.register(
            credentials.username, credentials.password.get_secret_value()
        )
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(status_code=400, detail="Username already exists") from exc
    result = await auth_service.users.get_with_statistics(user.id)
    if result is None:  # pragma: no cover
        raise RuntimeError("Created user could not be loaded")
    return ApiResponse(msg="register success", data=user_statistics_data(result))


@router.post("/admin", response_model=ApiResponse)
async def create_admin(
    credentials: Credentials,
    current_user: Annotated[User, Depends(require_admin)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> ApiResponse:
    del current_user
    try:
        user = await service.create_admin(
            credentials.username, credentials.password.get_secret_value()
        )
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(status_code=400, detail="Username already exists") from exc
    return ApiResponse(data={"user_id": str(user.id), "username": user.username})


@router.get("/", response_model=ApiResponse)
async def list_users(
    current_user: Annotated[User, Depends(require_admin)],
    service: Annotated[UserService, Depends(get_user_service)],
    page: Annotated[int | None, Query(ge=1)] = None,
    page_size: Annotated[int | None, Query(ge=1, le=1000)] = None,
) -> ApiResponse:
    del current_user
    try:
        total, users = await service.list_users(page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(
        data={"total": total, "users": [user_statistics_data(item) for item in users]}
    )


@router.put("/{user_id}/role", response_model=ApiResponse)
async def update_role(
    user_id: int,
    payload: RoleUpdateRequest,
    current_user: Annotated[User, Depends(require_admin)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> ApiResponse:
    try:
        user = await service.update_role(current_user, user_id, payload.role)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    except LastAdministratorError as exc:
        raise HTTPException(status_code=409, detail="cannot remove last administrator") from exc
    return ApiResponse(
        msg="role updated", data={"user_id": str(user.id), "role": user.role.value}
    )


@router.get("/{user_id}", response_model=ApiResponse)
async def get_user(
    user_id: int,
    current_user: Annotated[User, Depends(require_login)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> ApiResponse:
    try:
        result = await service.get_visible(current_user, user_id)
    except UserPermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return ApiResponse(data=user_statistics_data(result))
