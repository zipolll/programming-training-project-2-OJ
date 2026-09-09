"""Transactional editor saves; validation evidence stays server-owned."""

import json
from uuid import NAMESPACE_URL, uuid5

from backend.app.modules.agent.content import content_hash
from backend.app.modules.agent.models import AuthoringRequest, GeneratedProblem
from backend.app.modules.agent.repository import AgentRepository, RecordBusyError, _json, utc_now


async def save_editor_content(
    repository: AgentRepository,
    user_id: int,
    task_id: str,
    generated: GeneratedProblem,
    expected_hash: str,
    check_id: str | None = None,
    request_id: str | None = None,
) -> str:
    """request_id means explicit save-as; otherwise overwrite exactly this version."""
    candidate_hash = content_hash(generated)
    target_id = (
        str(uuid5(NAMESPACE_URL, f"editor-save:{user_id}:{request_id}")) if request_id else task_id
    )
    signature = _json([task_id, candidate_hash, expected_hash, check_id])
    now = utc_now().isoformat()
    async with repository.database.connect() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        cursor = await connection.execute(
            "SELECT * FROM agent_tasks WHERE task_id=? AND user_id=?",
            (task_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise LookupError("agent task not found")
        if row["workspace_kind"] or row["content_version_id"] != task_id:
            raise RecordBusyError("请打开对应的内容版本后保存。")
        if not (row["final_problem_json"] or row["draft_json"]):
            raise RecordBusyError("此任务尚无题目内容，请先完成生成。")
        if request_id:
            cursor = await connection.execute(
                "SELECT save_signature FROM agent_tasks WHERE task_id=?", (target_id,)
            )
            duplicate = await cursor.fetchone()
            if duplicate:
                if duplicate[0] != signature:
                    raise RecordBusyError("此请求标识已用于其他内容。")
                return target_id
        previous = GeneratedProblem.model_validate_json(
            row["final_problem_json"] or row["draft_json"]
        )
        previous_hash = content_hash(previous)
        if expected_hash != previous_hash and (request_id or candidate_hash != previous_hash):
            raise RecordBusyError("当前版本已在其他窗口修改，请重新加载后再保存。")
        cursor = await connection.execute(
            "SELECT 1 FROM agent_tasks WHERE record_id=? AND status IN ('pending','running')",
            (row["record_id"],),
        )
        if await cursor.fetchone():
            raise RecordBusyError("此记录已有正在运行的任务，请等待完成或停止。")
        report = None
        if check_id:
            cursor = await connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id=? AND user_id=? AND record_id=?",
                (check_id, user_id, row["record_id"]),
            )
            check = await cursor.fetchone()
            if check is None or check["workspace_kind"] != "check":
                raise RecordBusyError("验证记录不可用，请重新验证当前内容。")
            checked = GeneratedProblem.model_validate_json(check["input_draft_json"])
            if content_hash(checked) != candidate_hash:
                raise RecordBusyError("内容已变化，请重新验证或不附带旧验证结果保存。")
            if check["status"] not in ("success", "error", "cancelled"):
                raise RecordBusyError("验证尚未结束。")
            report = json.loads(check["validation_report_json"] or "null")
        elif candidate_hash == previous_hash:
            report = json.loads(row["validation_report_json"] or "null")
        passed = bool(
            report
            and report["reference_all_passed"]
            and report["samples_consistent"]
            and not report["blocking_errors"]
        )
        requirement_values = json.loads(row["request_json"])
        for key in ("difficulty", "problem_type", "time_limit", "memory_limit"):
            if getattr(generated.problem, key) != getattr(previous.problem, key):
                requirement_values[key] = getattr(generated.problem, key)
        if generated.problem.tags != previous.problem.tags:
            requirement_values["required_knowledge"] = generated.problem.tags
        if generated.problem.testcases != previous.problem.testcases:
            requirement_values["testcase_count"] = len(generated.problem.testcases)
        requirements = AuthoringRequest.model_validate(requirement_values)
        if request_id:
            cursor = await connection.execute(
                "SELECT COALESCE(MAX(revision),0)+1 FROM agent_tasks WHERE record_id=?",
                (row["record_id"],),
            )
            revision = (await cursor.fetchone())[0]
            await connection.execute(
                "INSERT INTO"
                " agent_tasks(task_id,user_id,parent_task_id,record_id,base_task_id,revision,"
                "status,stage,progress,request_json,currency,created_at,updated_at,operation,"
                "content_version_id,save_signature) VALUES"
                " (?,?,?,?,?,?,'success','awaiting_validation',100,?,?,?,?, 'edit',?,?)",
                (
                    target_id,
                    user_id,
                    task_id,
                    row["record_id"],
                    task_id,
                    revision,
                    _json(requirements.model_dump(exclude_unset=True)),
                    row["currency"],
                    now,
                    now,
                    target_id,
                    signature,
                ),
            )
        else:
            # Preserve what was imported before replacing this version's content.
            await connection.execute(
                "UPDATE agent_imports SET content_hash=? WHERE task_id=? AND content_hash IS NULL",
                (previous_hash, task_id),
            )
        await connection.execute(
            "UPDATE agent_tasks SET draft_json=?,final_problem_json=?,validation_report_json=?,"
            "request_json=?,effective_requirements_json='{}',status='success',stage=?,progress=100,"
            "error_code=NULL,safe_error_message=NULL,cancellation_requested=0,"
            "current_content_hash=?,updated_at=?,finished_at=? "
            "WHERE task_id=?",
            (
                _json(generated),
                _json(generated) if passed else None,
                _json(report) if report else None,
                _json(requirements.model_dump(exclude_unset=True)),
                "finalize" if passed else "awaiting_validation",
                candidate_hash,
                now,
                now,
                target_id,
            ),
        )
        await connection.execute(
            "INSERT INTO"
            " agent_events(task_id,stage,event_type,message,progress,timestamp) "
            "VALUES (?,?,'save',?,100,?)",
            (
                target_id,
                "finalize" if passed else "awaiting_validation",
                "另存为新版本" if request_id else "已覆盖保存当前版本",
                now,
            ),
        )
        await connection.commit()
    return target_id
