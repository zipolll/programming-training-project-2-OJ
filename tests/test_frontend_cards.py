"""Behavioral regressions for the shared responsive lists and form sections."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from frontend.components import layout
from frontend.pages.audit import audit_changes_summary

FIXTURE = Path(__file__).parent / "fixtures" / "card_pages.py"


def page_app(page: str) -> AppTest:
    app = AppTest.from_file(FIXTURE, default_timeout=15)
    app.session_state["fixture_page"] = page
    return app.run()


@pytest.mark.parametrize(
    "page",
    [
        "我的题库",
        "题库",
        "提交记录",
        "测试点",
        "用户管理",
        "访问审计",
        "普通命题",
        "编辑题目",
        "模型配置",
        "AI 命题",
        "语言注册",
        "代码提交",
        "题目内提交",
    ],
)
def test_card_pages_render_without_widget_or_context_errors(page: str) -> None:
    app = page_app(page)
    assert not app.exception


@pytest.mark.parametrize(
    ("changes", "action", "expected"),
    [
        ({}, "", "—"),
        (None, "", "—"),
        ([], "", "—"),
        ({"before": "user", "after": "admin"}, "update_user_role", "普通用户 → 管理员"),
        ({"before": False, "after": True}, "", "否 → 是"),
        ({"revision": 2, "model_name": "user"}, "", "版本：2；模型名称：user"),
        ({"public_cases": {"before": False, "after": True}}, "", "日志公开：否 → 是"),
        ({"future": {"nested": 0}}, "", "future：nested：0"),
        ({"before": None}, "", "原值：未设置"),
    ],
)
def test_audit_summaries_preserve_meaning(changes, action, expected) -> None:
    assert audit_changes_summary(changes, action) == expected


def test_audit_changes_removed_and_beijing_time_is_compact() -> None:
    app = page_app("访问审计")
    assert not app.exception
    details = [e for e in app.expander if e.label == "查看完整变更"]
    assert not details
    assert not app.json
    assert not any("变更摘要" in m.value for m in app.markdown)
    assert any("2026-09-04\n20:42:15" in m.value for m in app.markdown)
    assert len(audit_changes_summary({"long": "字" * 500})) == 100


def test_audit_pagination_uses_the_same_page_size_as_its_request() -> None:
    app = page_app("访问审计")
    assert any("第 1 / 2 页" in m.value for m in app.markdown)
    app.button(key="audit_history_page_2").click().run()
    path, params = app.session_state["fixture_last_get"]
    assert path == "/logs/audit/"
    assert params == {"page": 2, "page_size": 20}
    app.selectbox(key="audit_result_filter").select("失败").run()
    assert app.session_state["audit_history_page"] == 1
    assert app.session_state["fixture_last_get"][1]["success"] is False


def test_cell_text_escapes_user_content(monkeypatch) -> None:
    rendered = []
    monkeypatch.setattr(layout.st, "markdown", lambda body, **kw: rendered.append(body))
    layout.cell_text('<img src=x onerror="alert(1)">', emphasis=True)
    assert "<img" not in rendered[0]
    assert "&lt;img" in rendered[0]


def test_submission_selection_and_back_navigation_survive_cards() -> None:
    app = page_app("提交记录")
    app.button(key="history_submission_2").click().run()
    assert not app.exception
    assert app.query_params["submission"] == ["2"]
    assert any("评测详情 #2" in m.value for m in app.markdown)
    assert any("提交语言 · C++" in m.value for m in app.markdown)
    source = next(e for e in app.expander if e.label == "查看提交代码")
    assert not source.proto.expanded
    assert any("#include <iostream>" in block.value for block in app.code)
    assert app.metric[0].value == "编译错误"
    assert not any(b.label == "刷新一次" for b in app.button)
    next(b for b in app.button if b.label == "← 返回提交记录").click().run()
    assert "submission" not in app.query_params
    assert app.button(key="history_submission_2")


def test_problem_filters_and_link_remain_functional() -> None:
    app = page_app("题库")
    app.text_input(key="problem_list_search").input("不存在").run()
    assert any("没有找到" in m.value for m in app.markdown)
    app.text_input(key="problem_list_search").input("热搜").run()
    app.button(key="open_problem_hotword-ranking").click().run()
    assert not app.exception
    assert app.query_params["problem"] == ["hotword-ranking"]


@pytest.mark.parametrize(
    ("page", "total"),
    [("我的题库", 2), ("题库", 2), ("提交记录", 3), ("测试点", 7),
     ("用户管理", 3), ("访问审计", 23), ("语言注册", 2), ("题目内提交", 3)],
)
def test_lists_have_one_total_badge_without_page_badges(page, total):
    app = page_app(page)
    badge_blocks = [m.value for m in app.markdown if 'class="oj-badges"' in m.value]
    assert sum(f"共 {total} 条" in block for block in badge_blocks) == 1
    assert not any("第 " in block and " 页" in block for block in badge_blocks)


def test_edit_form_preserves_values_across_sample_and_testcase_changes() -> None:
    app = page_app("编辑题目")
    headings = "".join(m.value for m in app.markdown)
    titles = ["基本信息", "题面内容", "样例与测试点", "分类与资源限制"]
    positions = [headings.index(t) for t in titles]
    assert positions == sorted(positions)
    assert next(i for i in app.text_input if i.label == "题目 ID").disabled
    next(i for i in app.text_input if i.label == "标题").input("修改后的标题").run()
    app.button(key="fixture_samples_add").click().run()
    app.text_area(key="fixture_samples_1_in").input("new input")
    app.text_area(key="fixture_samples_1_out").input("new output").run()
    app.button(key="fixture_tests_add").click().run()
    app.button(key="fixture_tests_remove").click().run()
    app.button(key="fixture_save").click().run()
    assert not app.exception
    payload = app.session_state["fixture_payload"]
    assert payload["title"] == "修改后的标题"
    assert len(payload["samples"]) == 2
    assert payload["samples"][1] == {"input": "new input", "output": "new output"}
    assert len(payload["testcases"]) == 1
    assert payload["difficulty"] == "中等"
    assert payload["tags"] == ["模拟", "字符串", "哈希表"]


def test_all_lists_use_shared_layout_and_no_native_dataframes() -> None:
    root = Path(__file__).parents[1] / "frontend"
    for file in root.rglob("*.py"):
        text = file.read_text(encoding="utf-8")
        assert "st.dataframe(" not in text
        assert "st.table(" not in text
    for file in [
        "pages/problems.py",
        "pages/auth.py",
        "pages/submissions.py",
        "pages/audit.py",
        "components/submission_table.py",
    ]:
        text = (root / file).read_text(encoding="utf-8")
        assert "with data_table(" in text
        assert "with table_row(" in text


def test_standalone_submission_restores_problem_from_url() -> None:
    app = page_app("代码提交")
    app.selectbox(key="submission_problem").select("sum").run()
    assert not app.exception
    assert app.query_params["submission_problem"] == ["sum"]
    restored = page_app("代码提交")
    restored.query_params["submission_problem"] = "sum"
    restored.run()
    assert restored.selectbox(key="submission_problem").value == "sum"
    restored.query_params["submission_problem"] = "missing-problem"
    restored.run()
    assert not restored.exception
    assert restored.selectbox(key="submission_problem").value == "hotword-ranking"
