"""Safe, user-facing frontend exceptions."""

import re
from typing import Any

FIELD_LABELS = {
    "username": "用户名",
    "password": "密码",
    "confirmation": "确认密码",
    "problem_id": "题目 ID",
    "title": "标题",
    "description": "题面",
    "input_description": "输入说明",
    "output_description": "输出说明",
    "constraints": "约束",
    "samples": "样例",
    "testcases": "测试点",
    "language": "语言",
    "name": "语言名称",
    "file_ext": "源文件扩展名",
    "compile_cmd": "编译命令",
    "run_cmd": "运行命令",
    "code": "代码",
    "provider_url": "服务地址",
    "model_name": "模型名称",
    "api_key": "API Key",
    "required_knowledge": "必须覆盖的知识点",
    "difficulty": "目标难度",
    "problem_type": "题目类型",
    "expected_algorithm": "期望算法或复杂度",
    "data_scale": "数据规模",
    "feedback": "修改要求",
    "existing_problem_id": "已有题目",
    "user_id": "用户 ID",
    "page": "页码",
    "page_size": "每页数量",
}

MESSAGE_TRANSLATIONS = {
    "invalid username or password": "用户名或密码错误，请重新输入。",
    "user is banned": "该账号已被禁用，暂时无法使用。",
    "not authenticated": "登录已失效，请重新登录。",
    "permission denied": "你没有权限执行此操作。",
    "username already exists": "该用户名已被使用，请换一个试试。",
    "problem or language not found": "题目或编程语言不存在，请重新选择。",
    "submission rate limit exceeded": "提交过于频繁，请稍后再试。",
    "submission not found": "没有找到这条提交记录。",
    "problem not found": "没有找到这道题目。",
    "user not found": "没有找到该用户。",
    "agent task not found": "没有找到该命题任务。",
    "problem id already exists": "该题目 ID 已存在，请更换后重试。",
    "cannot remove last administrator": "必须至少保留一位管理员。",
    "manual confirmation is required": "请先确认已经完成人工审阅。",
    "task is not eligible for import": "当前任务还不能导入题库。",
    "invalid problem id": "题目 ID 格式不正确，请检查后重试。",
    "problem id does not match path": "题目 ID 与当前题目不一致。",
    "language already exists": "该语言已经注册，无需重复添加。",
    "invalid language configuration": "语言配置有误，请检查命令和占位符。",
}


def _field_from_location(location: Any) -> str | None:
    if not isinstance(location, (list, tuple)):
        return None
    for item in reversed(location):
        if isinstance(item, str) and item not in {"body", "query", "path"}:
            return item
    return None


def _validation_message(data: Any) -> str | None:
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    error = data[0]
    field = _field_from_location(error.get("loc"))
    label = FIELD_LABELS.get(field or "", "该项内容")
    descriptive_label = f"{label} " if label in {"题目 ID", "用户 ID", "API Key"} else label
    kind = str(error.get("type", "")).lower()
    if kind in {"missing", "string_too_short", "too_short"}:
        return f"请输入{label}。"
    if kind in {"string_too_long", "too_long"}:
        return f"{descriptive_label}内容过长，请适当精简。"
    if "greater_than" in kind or "less_than" in kind:
        return f"{descriptive_label}超出允许范围，请重新填写。"
    if kind in {"int_parsing", "float_parsing", "int_type", "float_type"}:
        return f"{descriptive_label}格式不正确，请填写有效数字。"
    return f"{descriptive_label}填写有误，请检查后重试。"


def _contains_chinese(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


class ApiError(Exception):
    def __init__(self, status_code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.data = data

    @property
    def user_message(self) -> str:
        validation = _validation_message(self.data)
        if validation:
            return validation
        translated = MESSAGE_TRANSLATIONS.get(self.message.strip().lower())
        if translated:
            return translated
        defaults = {
            400: "填写内容有误，请检查后重试。",
            401: "登录已失效，请重新登录。",
            403: "你没有权限执行此操作。",
            404: "没有找到相关内容。",
            409: "当前操作存在冲突，请刷新后重试。",
            429: "操作过于频繁，请稍后再试。",
            500: "服务暂时不可用，请稍后重试。",
            502: "服务暂时不可用，请稍后重试。",
            503: "服务暂时不可用，请稍后重试。",
        }
        if self.status_code in defaults:
            return defaults[self.status_code]
        if self.message and _contains_chinese(self.message):
            return self.message
        return "操作未完成，请稍后重试。"


class NetworkError(Exception):
    def __init__(self, message: str, *, is_timeout: bool = False) -> None:
        super().__init__(message)
        self.user_message = message
        self.is_timeout = is_timeout


class ProtocolError(ApiError):
    @property
    def user_message(self) -> str:
        return "服务响应异常，请稍后重试。"
