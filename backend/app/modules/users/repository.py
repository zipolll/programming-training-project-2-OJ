"""Persistence operations for users and login sessions."""

from datetime import datetime

import aiosqlite

from backend.app.core.database import Database
from backend.app.modules.users.models import User, UserRole, UserStatistics


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

    async def set_role_preserving_last_admin(self, user_id: int, role: UserRole) -> bool:
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute("SELECT role FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            if row is None:
                await connection.rollback()
                return False
            if row["role"] == UserRole.ADMIN.value and role is not UserRole.ADMIN:
                cursor = await connection.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin'"
                )
                count_row = await cursor.fetchone()
                if int(count_row[0]) <= 1:
                    await connection.rollback()
                    return False
            await connection.execute(
                "UPDATE users SET role = ? WHERE id = ?", (role.value, user_id)
            )
            await connection.commit()
        return True

    async def get_with_statistics(self, user_id: int) -> UserStatistics | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT u.*,
                       COUNT(s.submission_id) AS submit_count,
                       COUNT(DISTINCT CASE WHEN s.status = 'success' AND s.result = 'AC'
                                           THEN s.problem_id END) AS resolve_count
                FROM users AS u
                LEFT JOIN submissions AS s ON s.user_id = u.id AND s.statistics_excluded = 0
                WHERE u.id = ?
                GROUP BY u.id
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return UserStatistics(
            user=_deserialize_user(row),
            submit_count=int(row["submit_count"]),
            resolve_count=int(row["resolve_count"]),
        )

    async def list_with_statistics(
        self, *, page: int | None, page_size: int | None
    ) -> tuple[int, list[UserStatistics]]:
        async with self.database.connect() as connection:
            cursor = await connection.execute("SELECT COUNT(*) FROM users")
            total_row = await cursor.fetchone()
            sql = """
                SELECT u.*,
                       COUNT(s.submission_id) AS submit_count,
                       COUNT(DISTINCT CASE WHEN s.status = 'success' AND s.result = 'AC'
                                           THEN s.problem_id END) AS resolve_count
                FROM users AS u
                LEFT JOIN submissions AS s ON s.user_id = u.id AND s.statistics_excluded = 0
                GROUP BY u.id
                ORDER BY u.id
            """
            parameters: list[object] = []
            if page_size is not None:
                sql += " LIMIT ? OFFSET ?"
                parameters.extend((page_size, ((page or 1) - 1) * page_size))
            cursor = await connection.execute(sql, parameters)
            rows = await cursor.fetchall()
        users = [
            UserStatistics(
                user=_deserialize_user(row),
                submit_count=int(row["submit_count"]),
                resolve_count=int(row["resolve_count"]),
            )
            for row in rows
        ]
        return int(total_row[0]), users



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

    async def delete_for_user(self, user_id: int) -> None:
        async with self.database.connect() as connection:
            await connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            await connection.commit()


class AuthBridgeRepository:
    """Store only hashes for browser recovery tokens and one-time tickets."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_bridge(
        self,
        token_hash: str,
        session_id_hash: str,
        user_id: int,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO auth_bridges
                    (token_hash, session_id_hash, user_id, claimed, created_at, expires_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (
                    token_hash,
                    session_id_hash,
                    user_id,
                    _serialize_datetime(created_at),
                    _serialize_datetime(expires_at),
                ),
            )
            await connection.commit()

    async def claim_bridge(self, token_hash: str, now: datetime) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                UPDATE auth_bridges SET claimed = 1
                WHERE token_hash = ? AND claimed = 0 AND expires_at > ?
                """,
                (token_hash, _serialize_datetime(now)),
            )
            await connection.commit()
        return cursor.rowcount == 1

    async def get_bridge_user(self, token_hash: str, now: datetime) -> User | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT users.* FROM auth_bridges
                JOIN sessions ON sessions.id_hash = auth_bridges.session_id_hash
                JOIN users ON users.id = auth_bridges.user_id
                WHERE auth_bridges.token_hash = ?
                  AND auth_bridges.claimed = 1
                  AND auth_bridges.expires_at > ?
                  AND sessions.expires_at > ?
                """,
                (token_hash, _serialize_datetime(now), _serialize_datetime(now)),
            )
            row = await cursor.fetchone()
        return _deserialize_user(row) if row else None

    async def create_ticket(
        self,
        ticket_hash: str,
        bridge_hash: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO auth_bridge_tickets
                    (ticket_hash, bridge_hash, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    ticket_hash,
                    bridge_hash,
                    _serialize_datetime(created_at),
                    _serialize_datetime(expires_at),
                ),
            )
            await connection.commit()

    async def consume_ticket(self, ticket_hash: str, now: datetime) -> tuple[str, int] | None:
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT auth_bridge_tickets.bridge_hash, auth_bridges.user_id
                FROM auth_bridge_tickets
                JOIN auth_bridges
                  ON auth_bridges.token_hash = auth_bridge_tickets.bridge_hash
                JOIN sessions ON sessions.id_hash = auth_bridges.session_id_hash
                JOIN users ON users.id = auth_bridges.user_id
                WHERE auth_bridge_tickets.ticket_hash = ?
                  AND auth_bridge_tickets.expires_at > ?
                  AND auth_bridges.claimed = 1
                  AND auth_bridges.expires_at > ?
                  AND sessions.expires_at > ?
                  AND users.role != 'banned'
                """,
                (
                    ticket_hash,
                    _serialize_datetime(now),
                    _serialize_datetime(now),
                    _serialize_datetime(now),
                ),
            )
            row = await cursor.fetchone()
            await connection.execute(
                "DELETE FROM auth_bridge_tickets WHERE ticket_hash = ?", (ticket_hash,)
            )
            await connection.commit()
        if row is None:
            return None
        return str(row["bridge_hash"]), int(row["user_id"])

    async def update_session(self, bridge_hash: str, session_id_hash: str) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE auth_bridges SET session_id_hash = ? WHERE token_hash = ?",
                (session_id_hash, bridge_hash),
            )
            await connection.commit()

    async def delete_bridge(self, token_hash: str) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                "DELETE FROM auth_bridges WHERE token_hash = ?", (token_hash,)
            )
            await connection.commit()

    async def delete_for_session(self, session_id_hash: str) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                "DELETE FROM auth_bridges WHERE session_id_hash = ?", (session_id_hash,)
            )
            await connection.commit()

    async def delete_expired(self, now: datetime) -> None:
        serialized = _serialize_datetime(now)
        async with self.database.connect() as connection:
            await connection.execute(
                "DELETE FROM auth_bridge_tickets WHERE expires_at <= ?", (serialized,)
            )
            await connection.execute(
                "DELETE FROM auth_bridges WHERE expires_at <= ?", (serialized,)
            )
            await connection.commit()
