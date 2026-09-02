"""User registration and session authentication business logic."""

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import aiosqlite
import bcrypt

from backend.app.core.config import Settings
from backend.app.core.database import Database
from backend.app.modules.logs.audit_service import AuditService
from backend.app.modules.users.models import User, UserRole, UserStatistics
from backend.app.modules.users.repository import SessionRepository, UserRepository

INITIAL_ADMIN_USERNAME = "admin"
INITIAL_ADMIN_PASSWORD = "admintestpassword"


class UsernameAlreadyExistsError(Exception):
    """Raised when registration attempts to reuse a username."""


class InvalidCredentialsError(Exception):
    """Raised when a username/password pair is not valid."""


class BannedUserError(Exception):
    """Raised when a banned account attempts to sign in."""


class UserNotFoundError(Exception):
    pass


class UserPermissionError(Exception):
    pass


class LastAdministratorError(Exception):
    pass


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
        if user is None:
            await self.sessions.delete(id_hash)
            return None
        if user.role is UserRole.BANNED:
            await self.sessions.delete(id_hash)
            raise BannedUserError
        return user

    async def logout(self, session_id: str) -> None:
        await self.sessions.delete(_session_hash(session_id))


class UserService:
    """User lookup, statistics, administrator creation, and role policies."""

    def __init__(self, auth: AuthService, audit: AuditService) -> None:
        self.auth = auth
        self.users = auth.users
        self.sessions = auth.sessions
        self.audit = audit

    async def create_admin(self, username: str, password: str) -> User:
        password_hash = await _hash_password(password)
        try:
            return await self.users.create(
                username=username,
                password_hash=password_hash,
                role=UserRole.ADMIN,
                created_at=_utc_now(),
            )
        except aiosqlite.IntegrityError as exc:
            raise UsernameAlreadyExistsError from exc

    async def get_visible(self, actor: User, user_id: int) -> UserStatistics:
        if actor.role is not UserRole.ADMIN and actor.id != user_id:
            raise UserPermissionError
        result = await self.users.get_with_statistics(user_id)
        if result is None:
            raise UserNotFoundError
        return result

    async def list_users(
        self, *, page: int | None, page_size: int | None
    ) -> tuple[int, list[UserStatistics]]:
        if page is not None and page_size is None:
            raise ValueError("page_size is required when page is provided")
        return await self.users.list_with_statistics(page=page, page_size=page_size)

    async def update_role(self, actor: User, user_id: int, role: UserRole) -> User:
        target = await self.users.get_by_id(user_id)
        if target is None:
            raise UserNotFoundError
        if not await self.users.set_role_preserving_last_admin(user_id, role):
            raise LastAdministratorError
        if role is UserRole.BANNED:
            await self.sessions.delete_for_user(user_id)
        await self.audit.record(
            actor_user_id=actor.id,
            action="update_user_role",
            target_type="user",
            target_id=user_id,
            success=True,
            status=200,
            changes={"before": target.role.value, "after": role.value},
        )
        updated = await self.users.get_by_id(user_id)
        if updated is None:  # pragma: no cover
            raise RuntimeError("Updated user could not be loaded")
        return updated


def user_statistics_data(result: UserStatistics) -> dict[str, object]:
    return {
        "user_id": str(result.user.id),
        "username": result.user.username,
        "join_time": result.user.created_at.date().isoformat(),
        "role": result.user.role.value,
        "submit_count": result.submit_count,
        "resolve_count": result.resolve_count,
    }
