"""Persistence for structured security-audit records."""

import json
from datetime import datetime
from typing import Any

from backend.app.core.database import Database
from backend.app.modules.logs.audit_models import AuditLog


def _safe_changes(changes: dict[str, object] | None) -> str:
    return json.dumps(changes or {}, ensure_ascii=True, separators=(",", ":"))


def _from_row(row: Any) -> AuditLog:
    return AuditLog(
        id=row["id"],
        actor_user_id=row["actor_user_id"],
        action=row["action"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        success=bool(row["success"]),
        status=row["status"],
        changes=json.loads(row["changes"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        problem_id=row["problem_id"],
    )


class AuditRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        target_type: str,
        target_id: str,
        success: bool,
        status: int,
        changes: dict[str, object] | None,
        now: datetime,
    ) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO audit_logs
                    (actor_user_id, action, target_type, target_id, success,
                     status, changes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor_user_id,
                    action,
                    target_type,
                    target_id,
                    int(success),
                    status,
                    _safe_changes(changes),
                    now.isoformat(),
                ),
            )
            await connection.commit()

    async def list_access(
        self,
        *,
        user_id: int | None,
        problem_id: str | None,
        page: int | None,
        page_size: int | None,
    ) -> list[AuditLog]:
        clauses = ["a.action = 'view_logs'", "a.target_type = 'submission'"]
        parameters: list[object] = []
        if user_id is not None:
            clauses.append("a.actor_user_id = ?")
            parameters.append(user_id)
        if problem_id is not None:
            clauses.append("s.problem_id = ?")
            parameters.append(problem_id)
        sql = (
            "SELECT a.*, s.problem_id FROM audit_logs AS a "
            "JOIN submissions AS s ON s.submission_id = CAST(a.target_id AS INTEGER) "
            f"WHERE {' AND '.join(clauses)} ORDER BY a.created_at DESC, a.id DESC"
        )
        if page_size is not None:
            sql += " LIMIT ? OFFSET ?"
            parameters.extend((page_size, ((page or 1) - 1) * page_size))
        async with self.database.connect() as connection:
            cursor = await connection.execute(sql, parameters)
            rows = await cursor.fetchall()
        return [_from_row(row) for row in rows]
