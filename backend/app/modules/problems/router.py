"""Course-compatible problem management API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.app.core.responses import ApiResponse
from backend.app.modules.logs.audit_service import AuditService
from backend.app.modules.problems.models import Problem
from backend.app.modules.problems.service import (
    ProblemAlreadyExistsError,
    ProblemIdMismatchError,
    ProblemNotFoundError,
    ProblemService,
)
from backend.app.modules.users.dependencies import require_admin, require_login
from backend.app.modules.users.models import User

router = APIRouter()


async def get_problem_service(request: Request) -> ProblemService:
    return request.app.state.problem_service


async def get_audit_service(request: Request) -> AuditService:
    return request.app.state.audit_service


async def _parse_problem(request: Request) -> Problem:
    try:
        payload = await request.json()
        return Problem.model_validate(payload)
    except (ValueError, TypeError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request data") from exc


def _invalid_problem_id() -> HTTPException:
    return HTTPException(status_code=400, detail="invalid problem id")


@router.get("/", response_model=ApiResponse)
async def list_problems(
    current_user: Annotated[User, Depends(require_login)],
    problem_service: Annotated[ProblemService, Depends(get_problem_service)],
) -> ApiResponse:
    del current_user
    problems = await problem_service.list_problems()
    return ApiResponse(data=[problem.model_dump(mode="json") for problem in problems])


@router.post("/", response_model=ApiResponse)
async def add_problem(
    request: Request,
    current_user: Annotated[User, Depends(require_login)],
    problem_service: Annotated[ProblemService, Depends(get_problem_service)],
) -> ApiResponse:
    del current_user
    problem = await _parse_problem(request)
    try:
        await problem_service.create_problem(problem)
    except ProblemAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="problem id already exists") from exc
    return ApiResponse(msg="add success", data={"id": problem.id})


@router.put("/{problem_id}", response_model=ApiResponse)
async def update_problem(
    problem_id: str,
    request: Request,
    current_user: Annotated[User, Depends(require_login)],
    problem_service: Annotated[ProblemService, Depends(get_problem_service)],
) -> ApiResponse:
    del current_user
    problem = await _parse_problem(request)
    try:
        await problem_service.update_problem(problem_id, problem)
    except ValueError as exc:
        raise _invalid_problem_id() from exc
    except ProblemIdMismatchError as exc:
        raise HTTPException(status_code=400, detail="problem id does not match path") from exc
    except ProblemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="problem not found") from exc
    return ApiResponse(msg="update success", data={"id": problem.id})


@router.delete("/{problem_id}", response_model=ApiResponse)
async def delete_problem(
    problem_id: str,
    current_user: Annotated[User, Depends(require_admin)],
    problem_service: Annotated[ProblemService, Depends(get_problem_service)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> ApiResponse:
    try:
        await problem_service.delete_problem(problem_id)
    except ValueError as exc:
        raise _invalid_problem_id() from exc
    except ProblemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="problem not found") from exc
    await audit.record(
        actor_user_id=current_user.id,
        action="delete_problem",
        target_type="problem",
        target_id=problem_id,
        success=True,
        status=200,
    )
    return ApiResponse(msg="delete success", data={"id": problem_id})


@router.get("/{problem_id}", response_model=ApiResponse)
async def get_problem(
    problem_id: str,
    current_user: Annotated[User, Depends(require_login)],
    problem_service: Annotated[ProblemService, Depends(get_problem_service)],
) -> ApiResponse:
    del current_user
    try:
        problem = await problem_service.get_problem(problem_id)
    except ValueError as exc:
        raise _invalid_problem_id() from exc
    except ProblemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="problem not found") from exc
    return ApiResponse(data=problem.model_dump(mode="json"))
