"""Persistence for testcase logs, visibility settings, and audit records."""

from datetime import datetime

from backend.app.core.database import Database
from backend.app.modules.logs.models import EvaluationLogEntry


class EvaluationLogRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def list_current(self, submission_id: int) -> list[EvaluationLogEntry]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT t.*, s.finished_at FROM submission_testcases AS t
                JOIN submissions AS s ON s.submission_id = t.submission_id
                WHERE t.submission_id = ?
                  AND t.evaluation_version = s.evaluation_version
                ORDER BY t.testcase_id
                """,
                (submission_id,),
            )
            rows = await cursor.fetchall()
        return [
            EvaluationLogEntry(
                submission_id=row["submission_id"],
                evaluation_version=row["evaluation_version"],
                testcase_id=row["testcase_id"],
                result=row["result"],
                time=row["time"],
                memory=row["memory"],
                error_summary=row["error_summary"],
                completed_at=(
                    datetime.fromisoformat(row["finished_at"])
                    if row["finished_at"] is not None
                    else None
                ),
            )
            for row in rows
        ]

    async def is_public(self, problem_id: str) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT public_cases FROM problem_log_visibility WHERE problem_id = ?",
                (problem_id,),
            )
            row = await cursor.fetchone()
        return bool(row[0]) if row else False

    async def set_public(self, problem_id: str, public_cases: bool, now: datetime) -> bool:
        previous = await self.is_public(problem_id)
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO problem_log_visibility (problem_id, public_cases, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(problem_id) DO UPDATE SET
                    public_cases = excluded.public_cases,
                    updated_at = excluded.updated_at
                """,
                (problem_id, int(public_cases), now.isoformat()),
            )
            await connection.commit()
        return previous
