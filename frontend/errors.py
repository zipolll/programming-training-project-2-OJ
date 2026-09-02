"""Safe, user-facing frontend exceptions."""

from typing import Any


class ApiError(Exception):
    def __init__(self, status_code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.data = data

    @property
    def user_message(self) -> str:
        labels = {
            400: "请求参数有误",
            401: "登录已失效，请重新登录",
            403: "权限不足",
            404: "请求的内容不存在",
            409: "当前状态存在冲突",
            429: "操作过于频繁",
            500: "后端服务异常",
        }
        prefix = labels.get(self.status_code, f"请求失败（{self.status_code}）")
        return f"{prefix}：{self.message}" if self.message else prefix


class NetworkError(Exception):
    def __init__(self, message: str, *, is_timeout: bool = False) -> None:
        super().__init__(message)
        self.user_message = message
        self.is_timeout = is_timeout


class ProtocolError(ApiError):
    pass
