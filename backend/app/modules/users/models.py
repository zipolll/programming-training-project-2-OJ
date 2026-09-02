"""Internal user and session data models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    BANNED = "banned"


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: str
    role: UserRole
    created_at: datetime


class Credentials(BaseModel):
    """Credentials accepted by registration and login endpoints."""

    model_config = ConfigDict(str_strip_whitespace=False)

    username: str = Field(min_length=3, max_length=40)
    password: SecretStr = Field(min_length=6)


class PublicUser(BaseModel):
    """Safe user representation for API responses."""

    id: int
    username: str
    role: UserRole
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "PublicUser":
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            created_at=user.created_at,
        )


class RoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole


@dataclass(frozen=True)
class UserStatistics:
    user: User
    submit_count: int
    resolve_count: int
