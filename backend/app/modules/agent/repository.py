"""SQLite persistence for agent configuration, tasks, events, and usage."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from backend.app.core.database import Database
from backend.app.modules.agent.content import content_hash
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
        workspace_kind: str = "",
        input_draft: GeneratedProblem | None = None,
    ) -> AgentTask:
        now = utc_now()
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id=?", (task_id,)
            )
            existing = await cursor.fetchone()
            if existing is not None:
                if (
                    existing["user_id"] != user_id
                    or existing["request_json"]
                    != _json(request.model_dump(mode="json", exclude_unset=True))
                    or existing["workspace_kind"] != workspace_kind
                    or (
                        workspace_kind
                        and (
                            existing["input_draft_json"] != _json(input_draft)
                            or existing["feedback"] != feedback
                        )
                    )
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
                if generated:
                    cursor = await connection.execute(
                        "SELECT * FROM agent_tasks WHERE record_id=? AND user_id=? "
                        "ORDER BY created_at DESC LIMIT 1",
                        (record_id, user_id),
                    )
                    latest = await cursor.fetchone()
                    content = latest["final_problem_json"] or latest["draft_json"]
                    if content and GeneratedProblem.model_validate_json(content) == generated:
                        return self._task(dict(latest))
            if generated is None:
                revision = 0  # An execution becomes a version only after content exists.
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
            if generated is not None:
                await connection.execute(
                    "UPDATE agent_tasks SET content_version_id=task_id WHERE task_id=?",
                    (task_id,),
                )
            if workspace_kind:
                await connection.execute(
                    "UPDATE agent_tasks SET workspace_kind=?, input_draft_json=? WHERE task_id=?",
                    (workspace_kind, _json(input_draft), task_id),
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

    async def prepare_validation(self, task_id: str, user_id: int) -> bool:
        """Claim the existing content version atomically; duplicate validation is a no-op."""
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id=? AND user_id=?",
                (task_id, user_id),
            )
            row = await cursor.fetchone()
            if row is None:
                raise LookupError("agent task not found")
            if not (row["draft_json"] or row["final_problem_json"]):
                raise ValueError("尚无可验证的题目。")
            if row["status"] in ("pending", "running"):
                if row["validation_only"]:
                    return False
                raise RecordBusyError("此版本正在生成，请等待完成。")
            if row["status"] == "success" and row["final_problem_json"]:
                return False
            cursor = await connection.execute(
                "SELECT 1 FROM agent_tasks WHERE record_id=? AND status IN ('pending','running')",
                (row["record_id"],),
            )
            if await cursor.fetchone():
                raise RecordBusyError("此记录已有正在运行的任务，请等待完成或停止任务。")
            now = utc_now().isoformat()
            await connection.execute(
                "INSERT INTO agent_events(task_id,stage,event_type,message,progress,timestamp) "
                "VALUES (?, 'queued', 'validation', ?, 0, ?)",
                (
                    task_id,
                    _json(
                        {
                            "action": "验证当前版本",
                            "previous_status": row["status"],
                            "previous_report": json.loads(row["validation_report_json"] or "null"),
                            "previous_error": row["safe_error_message"],
                        }
                    ),
                    now,
                ),
            )
            await connection.execute(
                "UPDATE agent_tasks SET status='pending', stage='queued', progress=0, "
                "validation_only=1, execution_queued_at=?, updated_at=?, started_at=NULL, "
                "finished_at=NULL, cancellation_requested=0, error_code=NULL, "
                "safe_error_message=NULL, validation_report_json=NULL WHERE task_id=?",
                (now, now, task_id),
            )
            await connection.commit()
            return True

    async def store_draft(self, task_id: str, generated: GeneratedProblem) -> None:
        """Keep execution history but allocate a content version only for changed content."""
        encoded = _json(generated)
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id=? AND status IN ('pending','running')",
                (task_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return
            if row["workspace_kind"]:
                await connection.execute(
                    "UPDATE agent_tasks SET draft_json=?, updated_at=? WHERE task_id=?",
                    (encoded, utc_now().isoformat(), task_id),
                )
                await connection.commit()
                return
            cursor = await connection.execute(
                "SELECT task_id, content_version_id, revision FROM agent_tasks "
                "WHERE record_id=? AND task_id<>? "
                "AND (? IS NULL OR task_id=?) "
                "AND COALESCE(final_problem_json,draft_json)=? ORDER BY created_at LIMIT 1",
                (row["record_id"], task_id, row["base_task_id"], row["base_task_id"], encoded),
            )
            same = await cursor.fetchone()
            if same:
                revision = same["revision"]
                version_id = same["content_version_id"] or same["task_id"]
            else:
                cursor = await connection.execute(
                    "SELECT COALESCE(MAX(revision),0)+1 FROM agent_tasks "
                    "WHERE record_id=? AND task_id<>?",
                    (row["record_id"], task_id),
                )
                revision = (await cursor.fetchone())[0]
                version_id = task_id
            await connection.execute(
                "UPDATE agent_tasks SET draft_json=?, revision=?, content_version_id=?, "
                "updated_at=?, current_content_hash=? WHERE task_id=? "
                "AND status IN ('pending','running')",
                (
                    encoded,
                    revision,
                    version_id,
                    utc_now().isoformat(),
                    content_hash(generated),
                    task_id,
                ),
            )
            await connection.commit()

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
                    t.revision,t.content_version_id,t.validation_only,t.workspace_kind,t.feedback,
                    t.status,t.stage,t.progress,t.created_at,t.updated_at,
                    t.safe_error_message,t.error_code,t.cost,t.currency,t.total_tokens,
                    COALESCE(i.problem_id,vi.problem_id) AS imported_problem_id,
                    (COALESCE(i.content_hash,vi.content_hash) IS NULL OR
                     COALESCE(i.content_hash,vi.content_hash)=t.current_content_hash)
                        AS import_synced,
                    COALESCE(json_extract(t.final_problem_json,'$.problem.title'),
                        json_extract(t.draft_json,'$.problem.title'),'') AS title,
                    COALESCE(json_extract(t.final_problem_json,'$.problem.difficulty'),
                        json_extract(t.draft_json,'$.problem.difficulty'),
                        json_extract(t.request_json,'$.difficulty'),'') AS difficulty,
                    COALESCE(json_extract(t.request_json,'$.prompt'),
                        json_extract(t.request_json,'$.additional_requirements'),'') AS prompt,
                    COALESCE(json_extract(t.request_json,'$.required_knowledge'),'[]') AS knowledge,
                    (t.workspace_kind='' AND t.final_problem_json IS NOT NULL
                        AND t.status='success') AS usable,
                    (t.workspace_kind='' AND
                        (t.draft_json IS NOT NULL OR t.final_problem_json IS NOT NULL))
                        AS has_content
                FROM agent_tasks t LEFT JOIN agent_imports i ON i.task_id=t.task_id
                LEFT JOIN agent_imports vi ON vi.task_id=t.content_version_id
                WHERE t.user_id=? AND (? IS NULL OR t.record_id=?)
                ORDER BY t.created_at, t.revision, t.task_id
                """,
                (user_id, record_id, record_id),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def summarize_record(versions: list[dict[str, Any]]) -> dict[str, Any]:
        latest = max(versions, key=lambda version: version["updated_at"])
        if latest["workspace_kind"] and latest["status"] not in ("pending", "running"):
            latest = next((v for v in versions if v["task_id"] == latest["base_task_id"]), latest)
        content = next((v for v in reversed(versions) if v["has_content"]), latest)
        usable = next((v for v in reversed(versions) if v["usable"]), None)
        imported = next((v for v in reversed(versions) if v["imported_problem_id"]), None)
        active = next(
            (v for v in reversed(versions) if v["status"] in ("pending", "running")), None
        )
        root = next((v for v in versions if v["task_id"] == v["record_id"]), versions[0])
        return {
            "record_id": root["record_id"],
            "latest_task_id": latest["base_task_id"]
            if latest["workspace_kind"]
            else latest["task_id"],
            "active_task_id": active["task_id"] if active else None,
            "title": content["title"]
            or root["prompt"][:80]
            or "、".join(json.loads(root["knowledge"]))
            or "未命名出题",
            "prompt": root["prompt"],
            "difficulty": content["difficulty"],
            "status": "draft" if latest["stage"] == "awaiting_validation" else latest["status"],
            "display_status": "draft"
            if latest["stage"] == "awaiting_validation"
            else (
                "imported"
                if latest["status"] == "success"
                and latest["imported_problem_id"]
                and latest["import_synced"]
                else latest["status"]
            ),
            "stage": latest["stage"],
            "progress": latest["progress"],
            "version_count": len(
                {v["content_version_id"] or v["task_id"] for v in versions if v["has_content"]}
            ),
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
        display_status: str = "",
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
                and (not display_status or r["display_status"] == display_status)
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

    async def update_task(self, task_id: str, **values: Any) -> bool:
        """Freeze terminal executions so late work cannot overwrite timeout/cancellation."""
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
            cursor = await connection.execute(
                f"UPDATE agent_tasks SET {assignments} WHERE task_id = ? "  # noqa: S608
                "AND status IN ('pending', 'running')",
                (*converted.values(), task_id),
            )
            await connection.commit()
            return cursor.rowcount > 0

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
                "SELECT COALESCE(i.problem_id,vi.problem_id) FROM agent_tasks t "
                "LEFT JOIN agent_imports i ON i.task_id=t.task_id "
                "LEFT JOIN agent_imports vi ON vi.task_id=t.content_version_id WHERE t.task_id=?",
                (task_id,),
            )
            row = await cursor.fetchone()
        return str(row[0]) if row and row[0] is not None else None

    async def record_import(
        self, task_id: str, problem_id: str, fingerprint: str | None = None
    ) -> None:
        task = await self.get_task(task_id)
        assert task is not None
        fingerprint = fingerprint or content_hash(task.final_problem or task.draft)
        async with self.database.connect() as connection:
            await connection.execute(
                "INSERT INTO agent_imports(task_id,problem_id,imported_at,content_hash) "
                "SELECT COALESCE(content_version_id,task_id),?,?,? FROM agent_tasks"
                " WHERE task_id=? "
                "ON CONFLICT(task_id) DO UPDATE SET problem_id=excluded.problem_id, "
                "imported_at=excluded.imported_at,content_hash=excluded.content_hash",
                (problem_id, utc_now().isoformat(), fingerprint, task_id),
            )
            await connection.execute(
                "UPDATE agent_tasks SET current_content_hash=? WHERE (task_id=? OR"
                " content_version_id=?) AND current_content_hash IS NULL",
                (fingerprint, task_id, task.content_version_id or task_id),
            )
            await connection.commit()

    async def import_synced(self, task_id: str) -> bool:
        task = await self.get_task(task_id)
        if task is None:
            return False
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT content_hash FROM agent_imports WHERE task_id IN (?,?) ORDER BY"
                " task_id=? DESC LIMIT 1",
                (task_id, task.content_version_id or task_id, task_id),
            )
            row = await cursor.fetchone()
        return bool(
            row is not None
            and (row[0] is None or row[0] == content_hash(task.final_problem or task.draft))
        )

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
            content_version_id=row.get("content_version_id"),
            workspace_kind=row.get("workspace_kind", ""),
            input_draft=GeneratedProblem.model_validate_json(row["input_draft_json"])
            if row.get("input_draft_json")
            else None,
            validation_only=bool(row.get("validation_only")),
            execution_queued_at=datetime.fromisoformat(row["execution_queued_at"])
            if row.get("execution_queued_at")
            else None,
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
