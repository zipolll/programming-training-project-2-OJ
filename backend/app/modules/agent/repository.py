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


class RecordBusyError(ValueError):
    """Another execution already owns this record."""


class AgentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def get_config_row(self, user_id: int) -> dict[str, Any] | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM agent_config WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def save_config(
        self, user_id: int, config: AgentConfigUpdate, encrypted_api_key: str
    ) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO agent_config VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    provider_url=excluded.provider_url, model_name=excluded.model_name,
                    encrypted_api_key=excluded.encrypted_api_key,
                    input_price=excluded.input_price, output_price=excluded.output_price,
                    currency=excluded.currency, request_timeout=excluded.request_timeout,
                    max_iterations=excluded.max_iterations,
                    max_output_tokens=excluded.max_output_tokens, updated_at=excluded.updated_at
                """,
                (
                    user_id,
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
        base_task_id: str | None = None,
        operation: str = "generate",
        feedback: str = "",
        generated: GeneratedProblem | None = None,
        queued: bool = True,
    ) -> AgentTask:
        now = utc_now()
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id=?", (task_id,)
            )
            existing = await cursor.fetchone()
            if existing is not None:
                if existing["user_id"] != user_id or existing["request_json"] != _json(
                    request.model_dump(mode="json", exclude_unset=True)
                ):
                    raise RecordBusyError("请求标识已被其他内容使用，请重新提交。")
                return self._task(dict(existing))
            record_id = task_id
            if parent_task_id:
                cursor = await connection.execute(
                    "SELECT record_id FROM agent_tasks WHERE task_id=? AND user_id=?",
                    (parent_task_id, user_id),
                )
                parent = await cursor.fetchone()
                if parent is None:
                    raise LookupError("agent task not found")
                record_id = parent[0]
                cursor = await connection.execute(
                    "SELECT MAX(revision), SUM(status IN ('pending','running')) "
                    "FROM agent_tasks WHERE record_id=? AND user_id=?",
                    (record_id, user_id),
                )
                current = await cursor.fetchone()
                if current[1]:
                    raise RecordBusyError("此记录已有正在运行的任务，请等待完成或停止任务。")
                revision = current[0] + 1
            await connection.execute(
                """
                INSERT INTO agent_tasks
                (task_id,user_id,parent_task_id,revision,status,stage,progress,request_json,
                 cost,currency,created_at,updated_at,record_id,base_task_id,operation,
                 feedback,draft_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '0', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    user_id,
                    parent_task_id,
                    revision,
                    "pending" if queued else "success",
                    "queued" if queued else "awaiting_validation",
                    0 if queued else 100,
                    _json(request.model_dump(mode="json", exclude_unset=True)),
                    currency,
                    now.isoformat(),
                    now.isoformat(),
                    record_id,
                    base_task_id,
                    operation,
                    feedback,
                    _json(generated) if generated else None,
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

    async def record_versions(self, user_id: int, record_id: str) -> list[dict[str, Any]]:
        """Read version metadata only; never load test data or reference code for a list."""
        return await self._summaries(user_id, record_id)

    async def _summaries(
        self,
        user_id: int,
        record_id: str | None = None,
    ) -> list[dict[str, Any]]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT t.task_id,t.record_id,t.parent_task_id,t.base_task_id,t.operation,
                    t.revision,t.feedback,t.status,t.stage,t.progress,t.created_at,t.updated_at,
                    t.safe_error_message,t.error_code,t.cost,t.currency,t.total_tokens,
                    i.problem_id AS imported_problem_id,
                    COALESCE(json_extract(t.final_problem_json,'$.problem.title'),
                        json_extract(t.draft_json,'$.problem.title'),'') AS title,
                    COALESCE(json_extract(t.final_problem_json,'$.problem.difficulty'),
                        json_extract(t.draft_json,'$.problem.difficulty'),
                        json_extract(t.request_json,'$.difficulty'),'') AS difficulty,
                    COALESCE(json_extract(t.request_json,'$.prompt'),
                        json_extract(t.request_json,'$.additional_requirements'),'') AS prompt,
                    COALESCE(json_extract(t.request_json,'$.required_knowledge'),'[]') AS knowledge,
                    (t.final_problem_json IS NOT NULL AND t.status='success') AS usable,
                    (t.draft_json IS NOT NULL OR t.final_problem_json IS NOT NULL) AS has_content
                FROM agent_tasks t LEFT JOIN agent_imports i ON i.task_id=t.task_id
                WHERE t.user_id=? AND (? IS NULL OR t.record_id=?)
                ORDER BY t.created_at, t.revision, t.task_id
                """,
                (user_id, record_id, record_id),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def summarize_record(versions: list[dict[str, Any]]) -> dict[str, Any]:
        latest = versions[-1]
        content = next((v for v in reversed(versions) if v["has_content"]), latest)
        usable = next((v for v in reversed(versions) if v["usable"]), None)
        imported = next((v for v in reversed(versions) if v["imported_problem_id"]), None)
        active = next(
            (v for v in reversed(versions) if v["status"] in ("pending", "running")), None
        )
        root = versions[0]
        return {
            "record_id": root["record_id"],
            "latest_task_id": latest["task_id"],
            "active_task_id": active["task_id"] if active else None,
            "title": content["title"]
            or root["prompt"][:80]
            or "、".join(json.loads(root["knowledge"]))
            or "未命名出题",
            "prompt": root["prompt"],
            "difficulty": content["difficulty"],
            "status": "draft" if latest["stage"] == "awaiting_validation" else latest["status"],
            "stage": latest["stage"],
            "progress": latest["progress"],
            "version_count": len(versions),
            "updated_at": max(v["updated_at"] for v in versions),
            "usable_task_id": usable["task_id"] if usable else None,
            "editable_task_id": content["task_id"] if content["has_content"] else None,
            "imported_problem_id": imported["imported_problem_id"] if imported else None,
            "imported_task_id": imported["task_id"] if imported else None,
            "safe_error_message": latest["safe_error_message"],
        }

    async def list_records(
        self,
        user_id: int,
        *,
        search: str = "",
        status: str = "",
        difficulty: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for version in await self._summaries(user_id):
            groups.setdefault(version["record_id"], []).append(version)
        records = [self.summarize_record(versions) for versions in groups.values()]
        difficulties = sorted({r["difficulty"] for r in records if r["difficulty"]})
        query = search.strip().casefold()
        records = [
            r
            for r in records
            if (
                (not query or query in (r["title"] + " " + r["prompt"]).casefold())
                and (not status or r["status"] == status)
                and (not difficulty or r["difficulty"] == difficulty)
            )
        ]
        records.sort(key=lambda r: (r["updated_at"], r["record_id"]), reverse=True)
        return {
            "items": records[(page - 1) * page_size : page * page_size],
            "total": len(records),
            "difficulties": difficulties,
        }

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
            "effective_requirements_json",
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
            record_id=row.get("record_id") or row["task_id"],
            base_task_id=row.get("base_task_id"),
            operation=row.get("operation", "generate"),
            feedback=row.get("feedback", ""),
            effective_requirements=json.loads(row.get("effective_requirements_json") or "{}"),
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
