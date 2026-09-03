"""Authenticated, owner-isolated AI authoring API."""

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.core.responses import ApiResponse
from backend.app.modules.agent.client import ModelClientError, OpenAICompatibleClient
from backend.app.modules.agent.crypto import CredentialCipher, CredentialUnavailableError, mask_key
from backend.app.modules.agent.models import (
    AgentConfigUpdate,
    AgentConfigView,
    AgentStatus,
    AuthoringRequest,
    ImportRequest,
    RefineRequest,
    validate_provider_url,
)
from backend.app.modules.agent.repository import AgentRepository
from backend.app.modules.agent.task_manager import AgentTaskManager
from backend.app.modules.logs.audit_service import AuditService
from backend.app.modules.problems.service import (
    ProblemAlreadyExistsError,
    ProblemNotFoundError,
    ProblemService,
)
from backend.app.modules.users.dependencies import require_login
from backend.app.modules.users.models import User

router = APIRouter()


async def get_repository(request: Request) -> AgentRepository:
    return request.app.state.agent_repository


async def get_manager(request: Request) -> AgentTaskManager:
    return request.app.state.agent_task_manager


async def get_model_client(request: Request) -> OpenAICompatibleClient:
    return request.app.state.agent_model_client


async def get_problem_service(request: Request) -> ProblemService:
    return request.app.state.problem_service


async def get_audit_service(request: Request) -> AuditService:
    return request.app.state.audit_service


def _task_data(task: Any) -> dict[str, Any]:
    return task.model_dump(mode="json", exclude={"user_id"})


async def _owned_task(repository: AgentRepository, task_id: str, user_id: int):
    task = await repository.get_task(task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status_code=404, detail="agent task not found")
    return task


@router.get("/config", response_model=ApiResponse)
async def get_config(
    request: Request,
    current_user: Annotated[User, Depends(require_login)],
    repository: Annotated[AgentRepository, Depends(get_repository)],
) -> ApiResponse:
    row = await repository.get_config_row(current_user.id)
    configured = request.app.state.agent_cipher.configured
    if row is None:
        return ApiResponse(data={"configured": False, "encryption_configured": configured})
    view = AgentConfigView(
        provider_url=row["provider_url"],
        model_name=row["model_name"],
        masked_api_key=mask_key(bool(row["encrypted_api_key"])),
        has_api_key=bool(row["encrypted_api_key"]),
        encryption_configured=configured,
        input_price_per_million_tokens=Decimal(row["input_price"]),
        output_price_per_million_tokens=Decimal(row["output_price"]),
        currency=row["currency"],
        request_timeout=row["request_timeout"],
        max_iterations=row["max_iterations"],
        max_output_tokens=row["max_output_tokens"],
    )
    return ApiResponse(data={"configured": True, **view.model_dump(mode="json")})


@router.put("/config", response_model=ApiResponse)
async def save_config(
    payload: AgentConfigUpdate,
    request: Request,
    current_user: Annotated[User, Depends(require_login)],
    repository: Annotated[AgentRepository, Depends(get_repository)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> ApiResponse:
    try:
        validate_provider_url(
            payload.provider_url, request.app.state.settings.agent_allow_local_http
        )
        cipher: CredentialCipher = request.app.state.agent_cipher
        row = await repository.get_config_row(current_user.id)
        if payload.api_key is not None:
            encrypted = cipher.encrypt(payload.api_key)
        elif row is not None:
            encrypted = row["encrypted_api_key"]
        else:
            raise ValueError("api_key is required for initial configuration")
        await repository.save_config(current_user.id, payload, encrypted)
    except CredentialUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit.record(
        actor_user_id=current_user.id,
        action="update_agent_config",
        target_type="agent_config",
        target_id=str(current_user.id),
        success=True,
        status=200,
        changes={"model_name": payload.model_name, "provider_url": payload.provider_url},
    )
    return ApiResponse(msg="configuration saved", data={"has_api_key": True})


@router.post("/config/test", response_model=ApiResponse)
async def test_config(
    current_user: Annotated[User, Depends(require_login)],
    client: Annotated[OpenAICompatibleClient, Depends(get_model_client)],
) -> ApiResponse:
    try:
        result = await client.test_connection(current_user.id)
    except ModelClientError as exc:
        raise HTTPException(status_code=502, detail=exc.safe_message) from exc
    return ApiResponse(data={"connected": bool(result.content.get("ok", True))})


@router.post("/tasks", response_model=ApiResponse)
async def create_task(
    payload: AuthoringRequest,
    current_user: Annotated[User, Depends(require_login)],
    manager: Annotated[AgentTaskManager, Depends(get_manager)],
) -> ApiResponse:
    try:
        task_id = await manager.create(current_user.id, payload)
    except ModelClientError as exc:
        raise HTTPException(status_code=503, detail=exc.safe_message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(msg="task queued", data={"task_id": task_id, "status": "pending"})


@router.get("/tasks", response_model=ApiResponse)
async def list_tasks(
    current_user: Annotated[User, Depends(require_login)],
    repository: Annotated[AgentRepository, Depends(get_repository)],
) -> ApiResponse:
    tasks = await repository.list_tasks(current_user.id)
    return ApiResponse(data=[_task_data(task) for task in tasks])


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task(
    task_id: str,
    current_user: Annotated[User, Depends(require_login)],
    repository: Annotated[AgentRepository, Depends(get_repository)],
) -> ApiResponse:
    return ApiResponse(data=_task_data(await _owned_task(repository, task_id, current_user.id)))


@router.get("/tasks/{task_id}/events", response_model=ApiResponse)
async def get_events(
    task_id: str,
    current_user: Annotated[User, Depends(require_login)],
    repository: Annotated[AgentRepository, Depends(get_repository)],
    after_id: Annotated[int, Query(ge=0)] = 0,
) -> ApiResponse:
    await _owned_task(repository, task_id, current_user.id)
    events = await repository.list_events(task_id, after_id)
    return ApiResponse(data=[event.model_dump(mode="json") for event in events])


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse)
async def cancel_task(
    task_id: str,
    current_user: Annotated[User, Depends(require_login)],
    manager: Annotated[AgentTaskManager, Depends(get_manager)],
) -> ApiResponse:
    try:
        await manager.cancel(task_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="agent task not found") from exc
    return ApiResponse(msg="cancellation requested", data={"task_id": task_id})


@router.post("/tasks/{task_id}/refine", response_model=ApiResponse)
async def refine_task(
    task_id: str,
    payload: RefineRequest,
    current_user: Annotated[User, Depends(require_login)],
    manager: Annotated[AgentTaskManager, Depends(get_manager)],
) -> ApiResponse:
    try:
        new_task_id = await manager.refine(current_user.id, task_id, payload.feedback)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="agent task not found") from exc
    except ModelClientError as exc:
        raise HTTPException(status_code=503, detail=exc.safe_message) from exc
    return ApiResponse(msg="revision queued", data={"task_id": new_task_id, "status": "pending"})


@router.post("/tasks/{task_id}/import", response_model=ApiResponse)
async def import_task(
    task_id: str,
    payload: ImportRequest,
    current_user: Annotated[User, Depends(require_login)],
    repository: Annotated[AgentRepository, Depends(get_repository)],
    problem_service: Annotated[ProblemService, Depends(get_problem_service)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> ApiResponse:
    task = await _owned_task(repository, task_id, current_user.id)
    previous = await repository.get_import(task_id)
    if previous:
        return ApiResponse(msg="already imported", data={"problem_id": previous})
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="manual confirmation is required")
    if (
        task.status is not AgentStatus.SUCCESS
        or task.final_problem is None
        or task.validation_report is None
        or task.validation_report.blocking_errors
        or not task.validation_report.reference_all_passed
    ):
        raise HTTPException(status_code=409, detail="task is not eligible for import")
    problem = task.final_problem.problem
    try:
        if payload.update_existing:
            await problem_service.update_problem(problem.id, problem)
        else:
            await problem_service.create_problem(problem)
    except ProblemAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="problem id already exists") from exc
    except ProblemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="problem not found for update") from exc
    await repository.record_import(task_id, problem.id)
    await audit.record(
        actor_user_id=current_user.id,
        action="import_agent_problem",
        target_type="problem",
        target_id=problem.id,
        success=True,
        status=200,
        changes={"agent_task_id": task_id, "revision": task.revision},
    )
    return ApiResponse(msg="problem imported", data={"problem_id": problem.id})
