"""Course-compatible submission API for Steps 2 and 3."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.core.responses import ApiResponse
from backend.app.modules.judge.language_service import LanguageNotFoundError
from backend.app.modules.problems.service import ProblemNotFoundError
from backend.app.modules.submissions.models import SubmissionRequest, SubmissionStatus
from backend.app.modules.submissions.service import (
    SubmissionNotFoundError,
    SubmissionPermissionError,
    SubmissionRateLimitError,
    SubmissionService,
    submission_detail,
    submission_summary,
)
from backend.app.modules.users.dependencies import require_admin, require_login
from backend.app.modules.users.models import User

router = APIRouter()


async def get_submission_service(request: Request) -> SubmissionService:
    return request.app.state.submission_service


@router.post("/", response_model=ApiResponse)
async def create_submission(
    payload: SubmissionRequest,
    current_user: Annotated[User, Depends(require_login)],
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> ApiResponse:
    try:
        submission = await service.create(current_user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ProblemNotFoundError, LanguageNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="problem or language not found") from exc
    except SubmissionRateLimitError as exc:
        raise HTTPException(status_code=429, detail="submission rate limit exceeded") from exc
    return ApiResponse(data=submission_summary(submission))


@router.get("/", response_model=ApiResponse)
async def list_submissions(
    current_user: Annotated[User, Depends(require_login)],
    service: Annotated[SubmissionService, Depends(get_submission_service)],
    user_id: Annotated[int | None, Query(ge=1)] = None,
    problem_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    status: SubmissionStatus | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    page_size: Annotated[int | None, Query(ge=1, le=1000)] = None,
) -> ApiResponse:
    try:
        total, submissions = await service.list_visible(
            current_user,
            user_id=user_id,
            problem_id=problem_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SubmissionPermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    return ApiResponse(
        data={
            "total": total,
            "submissions": [submission_summary(item) for item in submissions],
        }
    )


@router.put("/{submission_id}/rejudge", response_model=ApiResponse)
async def rejudge_submission(
    submission_id: int,
    current_user: Annotated[User, Depends(require_admin)],
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> ApiResponse:
    del current_user
    try:
        submission = await service.rejudge(submission_id)
    except SubmissionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="submission not found") from exc
    return ApiResponse(msg="rejudge started", data=submission_summary(submission))


@router.get("/{submission_id}", response_model=ApiResponse)
async def get_submission(
    submission_id: int,
    current_user: Annotated[User, Depends(require_login)],
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> ApiResponse:
    try:
        submission = await service.get_visible(current_user, submission_id)
    except SubmissionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="submission not found") from exc
    except SubmissionPermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc
    return ApiResponse(data=submission_detail(submission))
