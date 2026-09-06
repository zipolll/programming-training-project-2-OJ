"""Structured audit recording and access-query policies."""

from datetime import datetime, timezone

from backend.app.modules.logs.audit_models import AuditLog
from backend.app.modules.logs.audit_repository import AuditRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditService:
    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    async def record(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        target_type: str,
        target_id: str | int,
        success: bool,
        status: int,
        changes: dict[str, object] | None = None,
    ) -> None:
        await self.repository.create(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            success=success,
            status=status,
            changes=changes,
            now=_utc_now(),
        )

    async def list_access(
        self,
        *,
        user_id: int | None,
        problem_id: str | None,
        page: int | None,
        page_size: int | None,
    ) -> list[AuditLog]:
        if user_id is None and problem_id is None:
            raise ValueError("user_id or problem_id is required")
        if page is not None and page_size is None:
            raise ValueError("page_size is required when page is provided")
        return await self.repository.list_access(
            user_id=user_id,
            problem_id=problem_id,
            page=page,
            page_size=page_size,
        )

    async def list_all(
        self,
        *,
        user_id: int | None,
        action: str | None,
        success: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[AuditLog]]:
        return await self.repository.list_all(
            user_id=user_id,
            action=action,
            success=success,
            page=page,
            page_size=page_size,
        )
