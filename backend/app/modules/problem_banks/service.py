"""Collection membership and atomic movement rules."""

from backend.app.modules.problem_banks.repository import BankError, BankRepository, timestamp
from backend.app.modules.problems.service import ProblemNotFoundError, ProblemService


class BankService:
    def __init__(self, repository: BankRepository, problems: ProblemService) -> None:
        self.repository = repository
        self.problems = problems

    async def create(self, user_id: int, name: str, description: str, ids: list[str]) -> int:
        """Commit a new collection and its initially selected problems together."""
        async with self.repository.transaction() as connection:
            for pid in ids:
                try:
                    await self.problems.get_problem(pid)
                except ProblemNotFoundError as exc:
                    raise BankError(404, f"题目 {pid} 不存在") from exc
            now = timestamp()
            cursor = await connection.execute(
                "INSERT INTO problem_banks (user_id, name, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, name, description, now, now),
            )
            bank_id = int(cursor.lastrowid)
            await connection.executemany(
                "INSERT INTO problem_bank_items (bank_id, problem_id) VALUES (?, ?)",
                [(bank_id, pid) for pid in dict.fromkeys(ids)],
            )
            return bank_id

    async def detail(self, user_id: int, bank_id: int) -> dict:
        bank, ids = await self.repository.detail(user_id, bank_id)
        summaries = {item.id: item.model_dump() for item in await self.problems.list_problems()}
        bank["problem_count"] = len(ids)
        bank["problems"] = [
            {**summaries[pid], "available": True}
            if pid in summaries
            else {"id": pid, "title": "题目已删除", "available": False}
            for pid in ids
        ]
        return bank

    async def change(
        self,
        user_id: int,
        bank_id: int,
        ids: list[str],
        action: str,
        target_bank_id: int | None = None,
    ) -> None:
        ids = list(dict.fromkeys(ids))
        async with self.repository.transaction() as connection:
            await self.repository.owned(connection, user_id, bank_id)
            if action == "move":
                await self.repository.owned(connection, user_id, target_bank_id)
                if target_bank_id == bank_id:
                    raise BankError(400, "请选择其他题库")
                rows = await (
                    await connection.execute(
                        "SELECT problem_id FROM problem_bank_items WHERE bank_id = ?",
                        (bank_id,),
                    )
                ).fetchall()
                if not set(ids).issubset({row[0] for row in rows}):
                    raise BankError(400, "选中的题目不在原题库中")
            if action != "remove":
                for pid in ids:
                    try:
                        await self.problems.get_problem(pid)
                    except ProblemNotFoundError as exc:
                        raise BankError(404, f"题目 {pid} 不存在") from exc
                destination = target_bank_id if action == "move" else bank_id
                await connection.executemany(
                    "INSERT OR IGNORE INTO problem_bank_items (bank_id, problem_id) VALUES (?, ?)",
                    [(destination, pid) for pid in ids],
                )
                await connection.execute(
                    "UPDATE problem_banks SET updated_at = ? WHERE id = ?",
                    (timestamp(), destination),
                )
            if action in {"remove", "move"}:
                await connection.executemany(
                    "DELETE FROM problem_bank_items WHERE bank_id = ? AND problem_id = ?",
                    [(bank_id, pid) for pid in ids],
                )
                await connection.execute(
                    "UPDATE problem_banks SET updated_at = ? WHERE id = ?",
                    (timestamp(), bank_id),
                )
