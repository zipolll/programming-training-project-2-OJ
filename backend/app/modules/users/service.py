"""User registration and session authentication business logic."""

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import aiosqlite
import bcrypt

from backend.app.core.config import Settings
from backend.app.core.database import Database
from backend.app.modules.users.models import User, UserRole
from backend.app.modules.users.repository import SessionRepository, UserRepository

INITIAL_ADMIN_USERNAME = "admin"
INITIAL_ADMIN_PASSWORD = "admintestpassword"


class UsernameAlreadyExistsError(Exception):
    """Raised when registration attempts to reuse a username."""


class InvalidCredentialsError(Exception):
    """Raised when a username/password pair is not valid."""


class BannedUserError(Exception):
    """Raised when a banned account attempts to sign in."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


async def _hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    hashed = await asyncio.to_thread(bcrypt.hashpw, password_bytes, bcrypt.gensalt())
    return hashed.decode("ascii")


async def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return await asyncio.to_thread(
            bcrypt.checkpw,
            password.encode("utf-8"),
            password_hash.encode("ascii"),
        )
    except (ValueError, UnicodeError):
        return False


class AuthService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.users = UserRepository(database)
        self.sessions = SessionRepository(database)
        self.settings = settings

    async def ensure_initial_admin(self) -> None:
        """Create the course-defined administrator only on the first startup."""
        if await self.users.get_by_username(INITIAL_ADMIN_USERNAME) is not None:
            return
        password_hash = await _hash_password(INITIAL_ADMIN_PASSWORD)
        try:
            await self.users.create(
                username=INITIAL_ADMIN_USERNAME,
                password_hash=password_hash,
                role=UserRole.ADMIN,
                created_at=_utc_now(),
            )
        except aiosqlite.IntegrityError:
            # Another application worker may have initialized the same database first.
            return

    async def register(self, username: str, password: str) -> User:
        password_hash = await _hash_password(password)
        try:
            return await self.users.create(
                username=username,
                password_hash=password_hash,
                role=UserRole.USER,
                created_at=_utc_now(),
            )
        except aiosqlite.IntegrityError as exc:
            raise UsernameAlreadyExistsError from exc

    async def login(self, username: str, password: str) -> tuple[User, str, datetime]:
        user = await self.users.get_by_username(username)
        if user is None or not await _verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        if user.role is UserRole.BANNED:
            raise BannedUserError

        now = _utc_now()
        expires_at = now + timedelta(seconds=self.settings.session_max_age_seconds)
        session_id = secrets.token_urlsafe(32)
        await self.sessions.create(_session_hash(session_id), user.id, now, expires_at)
        await self.sessions.delete_expired(now)
        return user, session_id, expires_at

    async def get_user_for_session(self, session_id: str) -> User | None:
        now = _utc_now()
        id_hash = _session_hash(session_id)
        user = await self.sessions.get_user(id_hash, now)
        if user is None or user.role is UserRole.BANNED:
            await self.sessions.delete(id_hash)
            return None
        return user

    async def logout(self, session_id: str) -> None:
        await self.sessions.delete(_session_hash(session_id))
