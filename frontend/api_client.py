"""Stateful HTTP client used by every Streamlit page."""

import os
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from frontend.errors import ApiError, NetworkError, ProtocolError

DEFAULT_API_BASE_URL = "http://localhost:8000/api"


class ApiClient:
    """Keep the backend cookie jar in memory and validate the API envelope."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
        on_unauthorized: Callable[[], None] | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("OJ_FRONTEND_API_BASE_URL", DEFAULT_API_BASE_URL)
        ).rstrip("/")
        self._on_unauthorized = on_unauthorized
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )

    @property
    def has_cookies(self) -> bool:
        """Report cookie presence without exposing cookie values."""
        return bool(self._client.cookies)

    def clear_cookies(self) -> None:
        self._client.cookies.clear()

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> dict[str, Any]:
        """Perform one request and return a validated ``code/msg/data`` envelope."""
        try:
            response = self._client.request(method, path, params=params, json=json)
        except httpx.TimeoutException as exc:
            raise NetworkError("请求超时，请稍后重试。", is_timeout=True) from exc
        except httpx.RequestError as exc:
            raise NetworkError("无法连接后端服务，请确认 FastAPI 已启动。") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProtocolError(response.status_code, "后端返回了非 JSON 响应。") from exc
        if (
            not isinstance(payload, dict)
            or {"code", "msg", "data"} - payload.keys()
            or not isinstance(payload.get("code"), int)
            or not isinstance(payload.get("msg"), str)
        ):
            raise ProtocolError(response.status_code, "后端响应格式不正确。")
        if payload["code"] != response.status_code:
            raise ProtocolError(response.status_code, "后端状态码与响应 code 不一致。")
        if response.status_code >= 400:
            if response.status_code == 401:
                self.clear_cookies()
                if self._on_unauthorized is not None:
                    self._on_unauthorized()
            raise ApiError(response.status_code, payload["msg"], payload.get("data"))
        return payload

    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, json: Any = None) -> dict[str, Any]:
        return self.request("POST", path, json=json)

    def put(self, path: str, *, json: Any = None) -> dict[str, Any]:
        return self.request("PUT", path, json=json)

    def delete(self, path: str) -> dict[str, Any]:
        return self.request("DELETE", path)

    def get_health(self) -> dict[str, Any]:
        return self.get("/health")
