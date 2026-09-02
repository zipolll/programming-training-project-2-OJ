"""Course Step 5 evaluation-log, visibility, and access-audit endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.core.responses import ApiResponse
from backend.app.modules.logs.audit_service import AuditService
from backend.app.modules.logs.models import LogVisibilityRequest
from backend.app.modules.logs.service import (
    EvaluationLogNotFoundError,
    EvaluationLogPermissionError,
    EvaluationLogService,
    evaluation_log_data,
)
from backend.app.modules.problems.service import ProblemNotFoundError
from backend.app.modules.users.dependencies import require_admin, require_login
from backend.app.modules.users.models import User

router = APIRouter()
submission_log_router = APIRouter()
problem_log_router = APIRouter()


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


@problem_log_router.put("/{problem_id}/log_visibility", response_model=ApiResponse)
async def update_log_visibility(
    problem_id: str,
    payload: LogVisibilityRequest,
    current_user: Annotated[User, Depends(require_admin)],
    service: Annotated[EvaluationLogService, Depends(get_log_service)],
) -> ApiResponse:
    try:
        await service.set_visibility(current_user, problem_id, payload.public_cases)
    except (ProblemNotFoundError, ValueError) as exc:
        status = 400 if isinstance(exc, ValueError) else 404
        message = "invalid problem id" if status == 400 else "problem not found"
        raise HTTPException(status_code=status, detail=message) from exc
    return ApiResponse(
        msg="log visibility updated",
        data={"problem_id": problem_id, "public_cases": payload.public_cases},
    )


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
                "action": "view_log",
                "time": entry.created_at.date().isoformat(),
                "status": str(entry.status),
            }
            for entry in entries
        ]
    )
