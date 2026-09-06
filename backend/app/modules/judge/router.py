"""Course-compatible language management API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.app.core.responses import ApiResponse
from backend.app.core.routing import CourseRoute
from backend.app.modules.judge.language_service import (
    LanguageAlreadyExistsError,
    LanguageService,
)
from backend.app.modules.judge.models import LanguageRegistration
from backend.app.modules.users.dependencies import require_login
from backend.app.modules.users.models import User

router = APIRouter(route_class=CourseRoute)


async def get_language_service(request: Request) -> LanguageService:
    return request.app.state.language_service


async def _parse_registration(request: Request) -> LanguageRegistration:
    try:
        payload = await request.json()
        registration = LanguageRegistration.model_validate(payload)
        registration.to_config()
        return registration
    except (TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid language configuration") from exc


@router.get("/", response_model=ApiResponse)
async def list_languages(
    language_service: Annotated[LanguageService, Depends(get_language_service)],
) -> ApiResponse:
    return ApiResponse(data={"name": await language_service.list_enabled_names()})


@router.post("/", response_model=ApiResponse)
async def register_language(
    request: Request,
    current_user: Annotated[User, Depends(require_login)],
    language_service: Annotated[LanguageService, Depends(get_language_service)],
) -> ApiResponse:
    del current_user
    registration = await _parse_registration(request)
    try:
        config = await language_service.register(registration)
    except LanguageAlreadyExistsError as exc:
        raise HTTPException(status_code=400, detail="language already exists") from exc
    return ApiResponse(msg="language registered", data={"name": config.name})
