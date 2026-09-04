"""Language registration page backed by the course language API."""

from typing import Any

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.common import OPTIONAL_PLACEHOLDER, REQUIRED_PLACEHOLDER, show_error
from frontend.components.ui import badges, page_header, section_header
from frontend.data_access import invalidate_language_cache, load_language_names


def validate_language(values: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(values.get("name", "")).strip():
        errors.append("请输入语言名称。")
    if not str(values.get("file_ext", "")).strip():
        errors.append("请输入源文件扩展名。")
    if not str(values.get("run_cmd", "")).strip():
        errors.append("请输入运行命令。")
    return errors


def render_language_registration(api: ApiClient) -> None:
    page_header(
        "注册新语言",
        "添加新的编译或解释执行环境。",
        icon="⌨️",
        eyebrow="LANGUAGE REGISTRY",
    )
    try:
        languages = load_language_names(api.base_url, api)
    except Exception as exc:
        show_error(exc)
        languages = []
    if languages:
        badges([(name, "cyan") for name in languages])

    section_header("语言配置", icon="🧰")
    with st.form("language_registration_form"):
        name = st.text_input("语言名称", placeholder="必填，如 java")
        file_ext = st.text_input("源文件扩展名", placeholder="必填，如 .java")
        compile_cmd = st.text_input(
            "编译命令",
            placeholder=OPTIONAL_PLACEHOLDER,
            help="编译型语言需包含 {src} 和 {exe}；解释型语言可留空。",
        )
        run_cmd = st.text_input(
            "运行命令",
            placeholder=REQUIRED_PLACEHOLDER,
            help="编译型语言使用 {exe}，解释型语言使用 {src}。",
        )
        limit_columns = st.columns(2)
        time_limit = limit_columns[0].number_input(
            "默认时间限制（秒）", min_value=0.01, max_value=60.0, value=1.0
        )
        memory_limit = limit_columns[1].number_input(
            "默认内存限制（MB）", min_value=1, max_value=4096, value=128
        )
        submitted = st.form_submit_button("注册语言", type="primary")
    if not submitted:
        return
    payload = {
        "name": name.strip(),
        "file_ext": file_ext.strip(),
        "compile_cmd": compile_cmd.strip() or None,
        "run_cmd": run_cmd.strip(),
        "time_limit": float(time_limit),
        "memory_limit": int(memory_limit),
    }
    errors = validate_language(payload)
    if errors:
        for message in errors:
            st.error(message)
        return
    try:
        result = api.post("/languages/", json=payload)["data"]
    except Exception as exc:
        show_error(exc)
    else:
        invalidate_language_cache()
        st.success(f"语言 {result['name']} 注册成功。")
