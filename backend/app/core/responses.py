"""Shared API response models."""

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """Common response envelope used by the course API."""

    code: int = 200
    msg: str = "success"
    data: Any = None
