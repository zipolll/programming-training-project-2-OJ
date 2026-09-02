"""Persistence operations for users and login sessions."""

from datetime import datetime

import aiosqlite

from backend.app.core.database import Database
from backend.app.modules.users.models import User, UserRole


def _serialize_datetime(value: datetime) -> str:
    return value.isoformat()


def _deserialize_user(row: aiosqlite.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        role=UserRole(row["role"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class UserRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(
        self,
        username: str,
        password_hash: str,
        role: UserRole,
        created_at: datetime,
    ) -> User:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, role.value, _serialize_datetime(created_at)),
            )
            await connection.commit()
            user_id = cursor.lastrowid
        if user_id is None:  # pragma: no cover - SQLite always returns an id here.
            raise RuntimeError("SQLite did not return a user id")
        user = await self.get_by_id(user_id)
        if user is None:  # pragma: no cover - protects against external database corruption.
            raise RuntimeError("Created user could not be loaded")
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
        return _deserialize_user(row) if row else None

    async def get_by_username(self, username: str) -> User | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = await cursor.fetchone()
        return _deserialize_user(row) if row else None

    async def set_role(self, user_id: int, role: UserRole) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE users SET role = ? WHERE id = ?", (role.value, user_id)
            )
            await connection.commit()


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(
        self,
        id_hash: str,
        user_id: int,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                "INSERT INTO sessions (id_hash, user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    id_hash,
                    user_id,
                    _serialize_datetime(created_at),
                    _serialize_datetime(expires_at),
                ),
            )
            await connection.commit()

    async def get_user(self, id_hash: str, now: datetime) -> User | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT users.* FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.id_hash = ? AND sessions.expires_at > ?
                """,
                (id_hash, _serialize_datetime(now)),
            )
            row = await cursor.fetchone()
        return _deserialize_user(row) if row else None

    async def delete(self, id_hash: str) -> None:
        async with self.database.connect() as connection:
            await connection.execute("DELETE FROM sessions WHERE id_hash = ?", (id_hash,))
            await connection.commit()

    async def delete_expired(self, now: datetime) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (_serialize_datetime(now),)
            )
            await connection.commit()
