"""Authenticated personal collection API."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.core.responses import ApiResponse
from backend.app.core.routing import CourseRoute
from backend.app.modules.problem_banks.models import (
    BankInput,
    CreateBankInput,
    MoveInput,
    ProblemIds,
)
from backend.app.modules.problem_banks.repository import BankError
from backend.app.modules.problem_banks.service import BankService
from backend.app.modules.users.dependencies import require_login
from backend.app.modules.users.models import User

router = APIRouter(route_class=CourseRoute)


async def service(request: Request) -> AsyncIterator[BankService]:
    try:
        yield request.app.state.bank_service
    except BankError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


CurrentUser = Annotated[User, Depends(require_login)]
Service = Annotated[BankService, Depends(service)]


@router.get("/", response_model=ApiResponse)
async def list_banks(user: CurrentUser, banks: Service) -> ApiResponse:
    return ApiResponse(data=await banks.repository.list_banks(user.id))


@router.post("/", response_model=ApiResponse)
async def create_bank(body: CreateBankInput, user: CurrentUser, banks: Service) -> ApiResponse:
    bank_id = await banks.create(user.id, body.name, body.description, body.problem_ids)
    return ApiResponse(data={"id": bank_id})


@router.get("/{bank_id}", response_model=ApiResponse)
async def detail(bank_id: int, user: CurrentUser, banks: Service) -> ApiResponse:
    return ApiResponse(data=await banks.detail(user.id, bank_id))


@router.put("/{bank_id}", response_model=ApiResponse)
async def update(bank_id: int, body: BankInput, user: CurrentUser, banks: Service) -> ApiResponse:
    await banks.repository.save(user.id, body.name, body.description, bank_id)
    return ApiResponse(data={"id": bank_id})


@router.delete("/{bank_id}", response_model=ApiResponse)
async def delete(bank_id: int, user: CurrentUser, banks: Service) -> ApiResponse:
    await banks.repository.delete(user.id, bank_id)
    return ApiResponse(data={"id": bank_id})


@router.post("/{bank_id}/problems", response_model=ApiResponse)
async def add(bank_id: int, body: ProblemIds, user: CurrentUser, banks: Service) -> ApiResponse:
    await banks.change(user.id, bank_id, body.problem_ids, "add")
    return ApiResponse(data={"id": bank_id})


@router.post("/{bank_id}/problems/remove", response_model=ApiResponse)
async def remove(bank_id: int, body: ProblemIds, user: CurrentUser, banks: Service) -> ApiResponse:
    await banks.change(user.id, bank_id, body.problem_ids, "remove")
    return ApiResponse(data={"id": bank_id})


@router.post("/{bank_id}/problems/move", response_model=ApiResponse)
async def move(bank_id: int, body: MoveInput, user: CurrentUser, banks: Service) -> ApiResponse:
    await banks.change(user.id, bank_id, body.problem_ids, "move", body.target_bank_id)
    return ApiResponse(data={"id": bank_id})
