"""Transactional asynchronous persistence for submissions and testcase results."""

from datetime import datetime
from typing import Any

from backend.app.core.database import Database
from backend.app.modules.judge.models import JudgeResult, TestcaseStatus
from backend.app.modules.submissions.models import Submission, SubmissionStatus


def _serialize_datetime(value: datetime) -> str:
    return value.isoformat()


def _deserialize_datetime(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _from_row(row: Any) -> Submission:
    return Submission(
        submission_id=row["submission_id"],
        user_id=row["user_id"],
        problem_id=row["problem_id"],
        language=row["language"],
        code=row["code"],
        status=SubmissionStatus(row["status"]),
        result=None if row["result"] is None else TestcaseStatus(row["result"]),
        score=row["score"],
        counts=row["counts"],
        compile_info=row["compile_info"],
        stdout=row["stdout"],
        stderr=row["stderr"],
        time=row["time"],
        memory=row["memory"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        finished_at=_deserialize_datetime(row["finished_at"]),
        evaluation_version=row["evaluation_version"],
    )


class SubmissionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(
        self,
        *,
        user_id: int,
        problem_id: str,
        language: str,
        code: str,
        counts: int,
        now: datetime,
    ) -> Submission:
        timestamp = _serialize_datetime(now)
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO submissions
                    (user_id, problem_id, language, code, status, counts,
                     created_at, updated_at, evaluation_version)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, 1)
                """,
                (user_id, problem_id, language, code, counts, timestamp, timestamp),
            )
            await connection.commit()
            submission_id = cursor.lastrowid
        if submission_id is None:  # pragma: no cover
            raise RuntimeError("SQLite did not return a submission id")
        submission = await self.get(submission_id)
        if submission is None:  # pragma: no cover
            raise RuntimeError("Created submission could not be loaded")
        return submission

    async def get(self, submission_id: int) -> Submission | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM submissions WHERE submission_id = ?", (submission_id,)
            )
            row = await cursor.fetchone()
        return None if row is None else _from_row(row)

    async def list_pending(self) -> list[tuple[int, int]]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT submission_id, evaluation_version FROM submissions
                WHERE status = 'pending' ORDER BY created_at, submission_id
                """
            )
            rows = await cursor.fetchall()
        return [(row["submission_id"], row["evaluation_version"]) for row in rows]

    async def count_recent(self, user_id: int, since: datetime) -> int:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT COUNT(*) FROM submissions WHERE user_id = ? AND created_at >= ?",
                (user_id, _serialize_datetime(since)),
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def list_filtered(
        self,
        *,
        user_id: int | None,
        problem_id: str | None,
        status: SubmissionStatus | None,
        page: int | None,
        page_size: int | None,
    ) -> tuple[int, list[Submission]]:
        clauses: list[str] = []
        parameters: list[object] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            parameters.append(user_id)
        if problem_id is not None:
            clauses.append("problem_id = ?")
            parameters.append(problem_id)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status.value)
        where = "" if not clauses else " WHERE " + " AND ".join(clauses)
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                f"SELECT COUNT(*) FROM submissions{where}", parameters
            )
            total_row = await cursor.fetchone()
            sql = (
                f"SELECT * FROM submissions{where} "
                "ORDER BY created_at DESC, submission_id DESC"
            )
            list_parameters = list(parameters)
            if page_size is not None:
                sql += " LIMIT ? OFFSET ?"
                list_parameters.extend((page_size, ((page or 1) - 1) * page_size))
            cursor = await connection.execute(sql, list_parameters)
            rows = await cursor.fetchall()
        return int(total_row[0]), [_from_row(row) for row in rows]

    async def complete_if_current(
        self,
        submission_id: int,
        evaluation_version: int,
        result: JudgeResult,
        now: datetime,
    ) -> bool:
        timestamp = _serialize_datetime(now)
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                UPDATE submissions SET status = 'success', result = ?, score = ?,
                    compile_info = ?, stdout = ?, stderr = ?, time = ?, memory = ?,
                    updated_at = ?, finished_at = ?
                WHERE submission_id = ? AND evaluation_version = ? AND status = 'pending'
                """,
                (
                    result.status.value,
                    result.score,
                    result.compile_info,
                    result.stdout,
                    result.stderr,
                    result.time,
                    result.memory,
                    timestamp,
                    timestamp,
                    submission_id,
                    evaluation_version,
                ),
            )
            if cursor.rowcount != 1:
                await connection.rollback()
                return False
            await connection.execute(
                "DELETE FROM submission_testcases WHERE submission_id = ?",
                (submission_id,),
            )
            await connection.executemany(
                """
                INSERT INTO submission_testcases
                    (submission_id, evaluation_version, testcase_id, result,
                     time, memory, error_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        submission_id,
                        evaluation_version,
                        item.id,
                        item.result.value,
                        item.time,
                        item.memory,
                        item.error_summary,
                    )
                    for item in result.testcase_results
                ],
            )
            await connection.commit()
        return True

    async def fail_if_current(
        self,
        submission_id: int,
        evaluation_version: int,
        message: str,
        now: datetime,
    ) -> bool:
        timestamp = _serialize_datetime(now)
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                UPDATE submissions SET status = 'error', result = NULL, score = NULL,
                    compile_info = NULL, stdout = NULL, stderr = ?, time = NULL,
                    memory = NULL, updated_at = ?, finished_at = ?
                WHERE submission_id = ? AND evaluation_version = ? AND status = 'pending'
                """,
                (message, timestamp, timestamp, submission_id, evaluation_version),
            )
            await connection.commit()
        return cursor.rowcount == 1

    async def begin_rejudge(self, submission_id: int, now: datetime) -> Submission | None:
        timestamp = _serialize_datetime(now)
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                UPDATE submissions SET status = 'pending', result = NULL, score = NULL,
                    compile_info = NULL, stdout = NULL, stderr = NULL, time = NULL,
                    memory = NULL, updated_at = ?, finished_at = NULL,
                    evaluation_version = evaluation_version + 1
                WHERE submission_id = ?
                """,
                (timestamp, submission_id),
            )
            if cursor.rowcount != 1:
                await connection.rollback()
                return None
            await connection.execute(
                "DELETE FROM submission_testcases WHERE submission_id = ?",
                (submission_id,),
            )
            await connection.commit()
        return await self.get(submission_id)
