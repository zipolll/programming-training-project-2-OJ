"""SQLite persistence for agent configuration, tasks, events, and usage."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from backend.app.core.database import Database
from backend.app.modules.agent.models import (
    AgentConfigUpdate,
    AgentEvent,
    AgentStatus,
    AgentTask,
    AuthoringRequest,
    GeneratedProblem,
    ValidationReport,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class AgentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def get_config_row(self) -> dict[str, Any] | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute("SELECT * FROM agent_config WHERE id = 1")
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def save_config(self, config: AgentConfigUpdate, encrypted_api_key: str) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO agent_config VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider_url=excluded.provider_url, model_name=excluded.model_name,
                    encrypted_api_key=excluded.encrypted_api_key,
                    input_price=excluded.input_price, output_price=excluded.output_price,
                    currency=excluded.currency, request_timeout=excluded.request_timeout,
                    max_iterations=excluded.max_iterations,
                    max_output_tokens=excluded.max_output_tokens, updated_at=excluded.updated_at
                """,
                (
                    config.provider_url,
                    config.model_name,
                    encrypted_api_key,
                    str(config.input_price_per_million_tokens),
                    str(config.output_price_per_million_tokens),
                    config.currency.upper(),
                    config.request_timeout,
                    config.max_iterations,
                    config.max_output_tokens,
                    utc_now().isoformat(),
                ),
            )
            await connection.commit()

    async def create_task(
        self,
        task_id: str,
        user_id: int,
        request: AuthoringRequest,
        *,
        parent_task_id: str | None = None,
        revision: int = 1,
        currency: str = "USD",
    ) -> AgentTask:
        now = utc_now()
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO agent_tasks
                (task_id,user_id,parent_task_id,revision,status,stage,progress,request_json,
                 cost,currency,created_at,updated_at)
                VALUES (?, ?, ?, ?, 'pending', 'queued', 0, ?, '0', ?, ?, ?)
                """,
                (
                    task_id,
                    user_id,
                    parent_task_id,
                    revision,
                    _json(request),
                    currency,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            await connection.commit()
        task = await self.get_task(task_id)
        assert task is not None
        return task

    async def get_task(self, task_id: str) -> AgentTask | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ?", (task_id,)
            )
            row = await cursor.fetchone()
        return self._task(dict(row)) if row else None

    async def list_tasks(self, user_id: int) -> list[AgentTask]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM agent_tasks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [self._task(dict(row)) for row in rows]

    async def list_pending(self) -> list[str]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT task_id FROM agent_tasks WHERE status = 'pending' ORDER BY created_at"
            )
            rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def recover_interrupted(self) -> None:
        now = utc_now().isoformat()
        async with self.database.connect() as connection:
            await connection.execute(
                """
                UPDATE agent_tasks SET status='error', stage='interrupted', progress=100,
                error_code='service_restarted',
                safe_error_message='Task was interrupted by a service restart',
                updated_at=?, finished_at=? WHERE status='running'
                """,
                (now, now),
            )
            await connection.commit()

    async def update_task(self, task_id: str, **values: Any) -> None:
        allowed = {
            "status",
            "stage",
            "progress",
            "draft_json",
            "final_problem_json",
            "validation_report_json",
            "error_code",
            "safe_error_message",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cost",
            "currency",
            "usage_estimated",
            "cancellation_requested",
            "started_at",
            "finished_at",
        }
        if not values or set(values) - allowed:
            raise ValueError("invalid agent task update")
        converted: dict[str, Any] = {}
        for key, value in values.items():
            if key.endswith("_json") and value is not None:
                value = _json(value)
            elif isinstance(value, (datetime, Decimal)):
                value = str(value) if isinstance(value, Decimal) else value.isoformat()
            elif isinstance(value, (bool, AgentStatus)):
                value = int(value) if isinstance(value, bool) else value.value
            converted[key] = value
        converted["updated_at"] = utc_now().isoformat()
        assignments = ", ".join(f"{key} = ?" for key in converted)
        async with self.database.connect() as connection:
            await connection.execute(
                f"UPDATE agent_tasks SET {assignments} WHERE task_id = ?",  # noqa: S608
                (*converted.values(), task_id),
            )
            await connection.commit()

    async def add_event(
        self, task_id: str, stage: str, event_type: str, message: str, progress: int
    ) -> AgentEvent:
        now = utc_now()
        safe_message = message[:1000]
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO agent_events(task_id,stage,event_type,message,progress,timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, stage, event_type, safe_message, progress, now.isoformat()),
            )
            await connection.commit()
            event_id = cursor.lastrowid
        assert event_id is not None
        return AgentEvent(
            event_id=event_id,
            task_id=task_id,
            stage=stage,
            event_type=event_type,
            message=safe_message,
            progress=progress,
            timestamp=now,
        )

    async def list_events(self, task_id: str, after_id: int = 0) -> list[AgentEvent]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM agent_events WHERE task_id = ? AND event_id > ?
                ORDER BY event_id LIMIT 200
                """,
                (task_id, after_id),
            )
            rows = await cursor.fetchall()
        return [
            AgentEvent(
                event_id=row["event_id"],
                task_id=row["task_id"],
                stage=row["stage"],
                event_type=row["event_type"],
                message=row["message"],
                progress=row["progress"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in rows
        ]

    async def add_usage(
        self,
        task_id: str,
        input_tokens: int,
        output_tokens: int,
        cost: Decimal,
        estimated: bool,
    ) -> None:
        total = input_tokens + output_tokens
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT input_tokens,output_tokens,total_tokens,cost,usage_estimated "
                "FROM agent_tasks WHERE task_id=?",
                (task_id,),
            )
            current = await cursor.fetchone()
            if current is None:
                raise ValueError("agent task does not exist")
            await connection.execute(
                """
                INSERT INTO agent_model_calls
                (task_id,input_tokens,output_tokens,total_tokens,cost,usage_estimated,created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    input_tokens,
                    output_tokens,
                    total,
                    str(cost),
                    int(estimated),
                    utc_now().isoformat(),
                ),
            )
            await connection.execute(
                """
                UPDATE agent_tasks SET input_tokens=?, output_tokens=?, total_tokens=?, cost=?,
                usage_estimated=?, updated_at=? WHERE task_id=?
                """,
                (
                    current["input_tokens"] + input_tokens,
                    current["output_tokens"] + output_tokens,
                    current["total_tokens"] + total,
                    str(Decimal(current["cost"]) + cost),
                    max(current["usage_estimated"], int(estimated)),
                    utc_now().isoformat(),
                    task_id,
                ),
            )
            await connection.commit()

    async def get_import(self, task_id: str) -> str | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT problem_id FROM agent_imports WHERE task_id=?", (task_id,)
            )
            row = await cursor.fetchone()
        return str(row[0]) if row else None

    async def record_import(self, task_id: str, problem_id: str) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                "INSERT OR IGNORE INTO agent_imports VALUES (?, ?, ?)",
                (task_id, problem_id, utc_now().isoformat()),
            )
            await connection.commit()

    @staticmethod
    def _task(row: dict[str, Any]) -> AgentTask:
        return AgentTask(
            task_id=row["task_id"],
            user_id=row["user_id"],
            parent_task_id=row["parent_task_id"],
            revision=row["revision"],
            status=AgentStatus(row["status"]),
            stage=row["stage"],
            progress=row["progress"],
            request=AuthoringRequest.model_validate_json(row["request_json"]),
            draft=GeneratedProblem.model_validate_json(row["draft_json"])
            if row["draft_json"]
            else None,
            final_problem=GeneratedProblem.model_validate_json(row["final_problem_json"])
            if row["final_problem_json"]
            else None,
            validation_report=ValidationReport.model_validate_json(row["validation_report_json"])
            if row["validation_report_json"]
            else None,
            error_code=row["error_code"],
            safe_error_message=row["safe_error_message"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            cost=Decimal(str(row["cost"])),
            currency=row["currency"],
            usage_estimated=bool(row["usage_estimated"]),
            cancellation_requested=bool(row["cancellation_requested"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        )
