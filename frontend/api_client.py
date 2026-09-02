"""HTTP client shared by Streamlit pages."""

import os
from typing import Any

import httpx

DEFAULT_API_BASE_URL = "http://localhost:8000/api"


class ApiClient:
    """Small wrapper that centralizes backend requests and errors."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (
            base_url or os.getenv("OJ_FRONTEND_API_BASE_URL", DEFAULT_API_BASE_URL)
        ).rstrip("/")

    def get_health(self) -> dict[str, Any]:
        """Fetch the backend health response."""
        with httpx.Client(base_url=self.base_url, timeout=5.0) as client:
            response = client.get("/health")
            response.raise_for_status()
            return response.json()
