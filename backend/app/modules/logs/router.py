"""Course Step 5 evaluation-log, visibility, and access-audit endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.core.responses import ApiResponse
from backend.app.core.routing import CourseRoute
from backend.app.modules.logs.audit_models import AuditLog
from backend.app.modules.logs.audit_service import AuditService
from backend.app.modules.logs.service import (
    EvaluationLogNotFoundError,
    EvaluationLogPermissionError,
    EvaluationLogService,
    evaluation_log_data,
)
from backend.app.modules.users.dependencies import require_admin, require_login
from backend.app.modules.users.models import User

router = APIRouter(route_class=CourseRoute)
submission_log_router = APIRouter(route_class=CourseRoute)


def _audit_log_data(entry: AuditLog) -> dict[str, object]:
    return {
        "id": str(entry.id),
        "user_id": str(entry.actor_user_id) if entry.actor_user_id is not None else None,
        "username": entry.actor_username,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "problem_id": entry.problem_id,
        "success": entry.success,
        "status": entry.status,
        "changes": entry.changes,
        "created_at": entry.created_at.isoformat(),
    }


async def get_log_service(request: Request) -> EvaluationLogService:
    return request.app.state.evaluation_log_service


async def get_audit_service(request: Request) -> AuditService:
    return request.app.state.audit_service


@submission_log_router.get("/{submission_id}/log", response_model=ApiResponse)
async def get_evaluation_log(
    submission_id: int,
    current_user: Annotated[User, Depends(require_login)],
    service: Annotated[EvaluationLogService, Depends(get_log_service)],
) -> ApiResponse:
    try:
        submission, entries = await service.get_visible(current_user, submission_id)
    except EvaluationLogNotFoundError as exc:
        raise HTTPException(status_code=404, detail="submission not found") from exc
    except EvaluationLogPermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    return ApiResponse(data=evaluation_log_data(submission, entries))


@router.get("/access/", response_model=ApiResponse)
async def list_log_access(
    current_user: Annotated[User, Depends(require_admin)],
    service: Annotated[AuditService, Depends(get_audit_service)],
    user_id: Annotated[int | None, Query(ge=1)] = None,
    problem_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    page_size: Annotated[int | None, Query(ge=1, le=1000)] = None,
) -> ApiResponse:
    del current_user
    try:
        entries = await service.list_access(
            user_id=user_id,
            problem_id=problem_id,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(
        data=[
            {
                "user_id": str(entry.actor_user_id),
                "problem_id": entry.problem_id,
                "action": "view_logs",
                "time": entry.created_at.date().isoformat(),
                "status": str(entry.status),
            }
            for entry in entries
        ]
    )


@router.get("/audit/", response_model=ApiResponse)
async def list_audit_logs(
    current_user: Annotated[User, Depends(require_admin)],
    service: Annotated[AuditService, Depends(get_audit_service)],
    user_id: Annotated[int | None, Query(ge=1)] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    success: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResponse:
    del current_user
    total, entries = await service.list_all(
        user_id=user_id,
        action=action,
        success=success,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(
        data={
            "total": total,
            "logs": [_audit_log_data(entry) for entry in entries],
        }
    )
