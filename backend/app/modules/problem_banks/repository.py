"""Owner-scoped SQLite collection storage."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from sqlite3 import IntegrityError

from backend.app.core.database import Database


class BankError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class BankRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @asynccontextmanager
    async def transaction(self):
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                await connection.commit()
            except IntegrityError as exc:
                await connection.rollback()
                raise BankError(409, "题库名称已存在") from exc
            except BaseException:
                await connection.rollback()
                raise

    async def owned(self, connection, user_id: int, bank_id: int) -> dict:
        row = await (
            await connection.execute(
                "SELECT * FROM problem_banks WHERE id = ? AND user_id = ?",
                (bank_id, user_id),
            )
        ).fetchone()
        if row is None:
            raise BankError(404, "题库不存在")
        return dict(row)

    async def list_banks(self, user_id: int) -> list[dict]:
        async with self.database.connect() as connection:
            rows = await (
                await connection.execute(
                    """SELECT b.*, COUNT(p.problem_id) AS problem_count FROM problem_banks b
                LEFT JOIN problem_bank_items p ON p.bank_id = b.id
                WHERE b.user_id = ? GROUP BY b.id ORDER BY b.created_at DESC, b.id DESC""",
                    (user_id,),
                )
            ).fetchall()
            return [dict(row) for row in rows]

    async def save(self, user_id: int, name: str, description: str, bank_id=None) -> int:
        async with self.transaction() as connection:
            now = timestamp()
            if bank_id is None:
                cursor = await connection.execute(
                    """INSERT INTO problem_banks
                    (user_id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)""",
                    (user_id, name, description, now, now),
                )
                return int(cursor.lastrowid)
            await self.owned(connection, user_id, bank_id)
            await connection.execute(
                "UPDATE problem_banks SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (name, description, now, bank_id),
            )
            return bank_id

    async def delete(self, user_id: int, bank_id: int) -> None:
        async with self.transaction() as connection:
            await self.owned(connection, user_id, bank_id)
            await connection.execute("DELETE FROM problem_banks WHERE id = ?", (bank_id,))

    async def detail(self, user_id: int, bank_id: int) -> tuple[dict, list[str]]:
        async with self.database.connect() as connection:
            await connection.execute("BEGIN")
            bank = await self.owned(connection, user_id, bank_id)
            rows = await (
                await connection.execute(
                    "SELECT problem_id FROM problem_bank_items "
                    "WHERE bank_id = ? ORDER BY problem_id",
                    (bank_id,),
                )
            ).fetchall()
            return bank, [row[0] for row in rows]
