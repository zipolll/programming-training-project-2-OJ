"""Pure data conversion and validation helpers for frontend forms."""

import re
from typing import Any

PROBLEM_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

NAVIGATION_LAYOUT = {
    "概览": ("首页",),
    "题目": ("题目列表", "题目管理"),
    "评测": ("提交记录", "注册新语言", "日志可见性"),
    "账户": ("注册", "登录", "个人信息", "用户管理", "退出"),
}

NAVIGATION_METADATA = {
    "首页": {"icon": ":material/home:", "url_path": "home"},
    "题目列表": {"icon": ":material/list_alt:", "url_path": "problems"},
    "题目管理": {"icon": ":material/edit_document:", "url_path": "problem-management"},
    "提交记录": {"icon": ":material/history:", "url_path": "submissions"},
    "注册新语言": {"icon": ":material/terminal:", "url_path": "languages"},
    "日志可见性": {"icon": ":material/visibility:", "url_path": "log-visibility"},
    "注册": {"icon": ":material/person_add:", "url_path": "register"},
    "登录": {"icon": ":material/login:", "url_path": "login"},
    "个人信息": {"icon": ":material/person:", "url_path": "profile"},
    "用户管理": {"icon": ":material/manage_accounts:", "url_path": "users"},
    "退出": {"icon": ":material/logout:", "url_path": "logout"},
}


def validate_registration(username: str, password: str, confirmation: str) -> list[str]:
    errors = []
    if not username.strip():
        errors.append("请输入用户名。")
    elif not 3 <= len(username) <= 40:
        errors.append("用户名长度应为 3–40 个字符。")
    if not password:
        errors.append("请输入密码。")
    elif len(password) < 6:
        errors.append("密码至少需要 6 个字符。")
    if not confirmation:
        errors.append("请再次输入密码。")
    elif password != confirmation:
        errors.append("两次输入的密码不一致。")
    return errors


def validate_login(username: str, password: str) -> list[str]:
    errors = []
    if not username.strip():
        errors.append("请输入用户名。")
    elif len(username.strip()) < 3:
        errors.append("用户不存在。")
    if not password:
        errors.append("请输入密码。")
    return errors


def validate_problem(problem: dict[str, Any]) -> list[str]:
    errors = []
    if not PROBLEM_ID_PATTERN.fullmatch(str(problem.get("id", ""))):
        errors.append("题目 ID 只能包含字母、数字、下划线和连字符，最长 64 位。")
    for field, label in (
        ("title", "标题"),
        ("description", "题面"),
        ("input_description", "输入说明"),
        ("output_description", "输出说明"),
        ("constraints", "约束"),
    ):
        if not str(problem.get(field, "")).strip():
            errors.append(f"请输入{label}。")
    if not problem.get("samples"):
        errors.append("至少需要一个样例。")
    if not problem.get("testcases"):
        errors.append("至少需要一个测试点。")
    if float(problem.get("time_limit", 0)) <= 0:
        errors.append("时间限制必须大于 0。")
    if int(problem.get("memory_limit", 0)) <= 0:
        errors.append("内存限制必须大于 0。")
    return errors


def build_problem_payload(values: dict[str, Any]) -> dict[str, Any]:
    """Build the exact course Problem structure from stable form values."""
    return {
        "id": str(values.get("id", "")).strip(),
        "title": str(values.get("title", "")).strip(),
        "description": str(values.get("description", "")),
        "input_description": str(values.get("input_description", "")),
        "output_description": str(values.get("output_description", "")),
        "samples": [dict(item) for item in values.get("samples", [])],
        "constraints": str(values.get("constraints", "")),
        "testcases": [dict(item) for item in values.get("testcases", [])],
        "hint": str(values.get("hint", "")),
        "source": str(values.get("source", "")),
        "tags": [tag.strip() for tag in values.get("tags", []) if tag.strip()],
        "time_limit": float(values.get("time_limit", 3.0)),
        "memory_limit": int(values.get("memory_limit", 128)),
        "author": str(values.get("author", "")),
        "difficulty": str(values.get("difficulty", "")),
    }


def navigation_for(role: str | None) -> list[str]:
    if role is None:
        return ["首页", "注册", "登录"]
    pages = [
        "首页",
        "题目列表",
        "题目管理",
        "提交记录",
        "注册新语言",
        "个人信息",
        "退出",
    ]
    if role == "admin":
        pages.insert(-2, "用户管理")
        pages.insert(-2, "日志可见性")
    return pages


def navigation_sections(role: str | None) -> dict[str, list[str]]:
    """Group the pages visible to a role without hiding links behind a selector."""
    visible_pages = set(navigation_for(role))
    sections = {}
    for section, pages in NAVIGATION_LAYOUT.items():
        visible_in_section = [page for page in pages if page in visible_pages]
        if visible_in_section:
            sections[section] = visible_in_section
    return sections


def should_poll(status: str | None) -> bool:
    return status == "pending"


def status_text(status: str | None) -> str:
    return {
        "pending": "等待评测（pending）",
        "success": "评测完成（success）",
        "error": "评测异常（error）",
        "AC": "答案正确（AC）",
        "WA": "答案错误（WA）",
        "CE": "编译错误（CE）",
        "RE": "运行错误（RE）",
        "TLE": "时间超限（TLE）",
        "MLE": "内存超限（MLE）",
        "UNK": "未知错误（UNK）",
    }.get(status or "", status or "未知")
