"""Real Streamlit interactions backed by the collection API."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from backend.app.core.config import Settings
from backend.app.main import create_app
from frontend.errors import ApiError
from frontend.session import clear_auth, set_auth_user

FIXTURE = Path(__file__).parent / "fixtures" / "bank_pages.py"


class Adapter:
    base_url = "http://test-bank-api"

    def __init__(self, client):
        self.client = client
        self.fail = False

    def request(self, method, path, **kwargs):
        if self.fail and method == "POST":
            raise RuntimeError("模拟网络故障")
        response = self.client.request(method, "/api" + path, **kwargs)
        if response.status_code != 200:
            raise ApiError(response.status_code, response.json()["msg"])
        return response.json()

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path):
        return self.request("DELETE", path)


@pytest.fixture
def ui(tmp_path):
    settings = Settings(
        database_path=tmp_path / "oj.db", problems_path=tmp_path / "problems", environment="test"
    )
    with TestClient(create_app(settings)) as client:
        credentials = {"username": "alice", "password": "secret1"}
        client.post("/api/users/", json=credentials)
        client.post("/api/auth/login", json=credentials)
        for number in range(12):
            client.post(
                "/api/problems/",
                json={
                    "id": f"P{number:02}",
                    "title": f"Problem {number}",
                    "description": "Add",
                    "input_description": "Numbers",
                    "output_description": "Sum",
                    "constraints": "Small",
                    "samples": [{"input": "1 2", "output": "3"}],
                    "testcases": [{"input": "1 2", "output": "3"}],
                    "difficulty": "简单",
                },
            )
        api = Adapter(client)
        app = AppTest.from_file(FIXTURE, default_timeout=15)
        app.session_state["test_api"] = api
        yield app, api


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_public_catalogue_has_no_collection_actions(ui):
    app, api = ui
    app.session_state["test_page"] = "catalogue"
    app.run()
    assert not app.exception
    assert not app.checkbox
    assert not any(b.label in {"添加到题库", "增加题目", "创建题库"} for b in app.button)
    assert any("共 12 条" in m.value for m in app.markdown)


def test_create_draft_add_page_preserves_metadata_and_selection(ui):
    app, api = ui
    app.run()
    button(app, "创建题库").click().run()
    app.text_input(key="bank_draft_new_widget_name").set_value("训练").run()
    app.text_area(key="bank_draft_new_widget_description").set_value("本周练习").run()
    button(app, "增加题目").click().run()
    assert not app.exception
    assert app.query_params["bank_view"] == ["add"]
    assert not any(c.label == "全选当前页" for c in app.checkbox)
    app.checkbox(key="bank_selection_bank_add_new_item_P00").check().run()
    app.button(key="bank_add_new_next").click().run()
    assert button(app, "确认增加").disabled
    app.checkbox(key="bank_selection_bank_add_new_item_P10").check().run()
    app.text_input(key="bank_add_new_search").set_value("P00").run()
    assert button(app, "确认增加").disabled
    app.checkbox(key="bank_selection_bank_add_new_item_P00").check().run()
    button(app, "确认增加").click().run()
    assert not app.exception
    assert app.text_input(key="bank_draft_new_widget_name").value == "训练"
    assert app.text_area(key="bank_draft_new_widget_description").value == "本周练习"
    assert api.get("/problem-banks/")["data"] == []
    button(app, "增加题目").click().run()
    # The first selection is retained in the draft and excluded from available problems.
    assert not any(c.label == "选择 P00" for c in app.checkbox)
    app.text_input(key="bank_add_new_search").set_value("P01").run()
    app.checkbox(key="bank_selection_bank_add_new_item_P01").check().run()
    button(app, "确认增加").click().run()
    api.fail = True
    button(app, "保存题库").click().run()
    assert app.error
    assert app.text_input(key="bank_draft_new_widget_name").value == "训练"
    api.fail = False
    button(app, "保存题库").click().run()
    assert not app.exception
    bank = api.get("/problem-banks/")["data"][0]
    assert (bank["name"], bank["description"], bank["problem_count"]) == ("训练", "本周练习", 2)
    assert "bank_view" not in app.query_params
    assert not app.checkbox
    assert not any(b.label in {"增加题目", "移出题库", "移动到其他题库"} for b in app.button)
    assert any("本周练习" in m.value for m in app.markdown)


def test_edit_add_remove_and_delete_are_separate_from_browsing(ui):
    app, api = ui
    source = api.post("/problem-banks/", json={"name": "Source"})["data"]["id"]
    target = api.post("/problem-banks/", json={"name": "Target"})["data"]["id"]
    api.post(f"/problem-banks/{source}/problems", json={"problem_ids": ["P00", "P01"]})
    app.run()
    assert not any(b.label == "打开题库" for b in app.button)
    button(app, "Source").click().run()
    assert not app.checkbox
    app.button(key=f"bank_{source}_open_P00").click().run()
    assert button(app, "去提交")
    button(app, "← 返回当前题库").click().run()
    button(app, "编辑题库").click().run()
    assert not app.exception
    app.text_input(key=f"bank_draft_{source}_widget_name").set_value("复习").run()
    app.text_area(key=f"bank_draft_{source}_widget_description").set_value("本周计划").run()
    button(app, "增加题目").click().run()
    assert not any(c.label == "选择 P00" for c in app.checkbox)
    app.checkbox(key=f"bank_selection_bank_add_{source}_item_P02").check().run()
    api.fail = True
    button(app, "确认增加").click().run()
    assert app.error
    assert api.get(f"/problem-banks/{source}")["data"]["problem_count"] == 2
    api.fail = False
    button(app, "确认增加").click().run()
    assert app.text_input(key=f"bank_draft_{source}_widget_name").value == "复习"
    button(app, "保存名称与描述").click().run()
    assert api.get(f"/problem-banks/{source}")["data"]["name"] == "复习"
    button(app, "编辑题库").click().run()
    assert not app.checkbox
    assert not any(b.label == "移动到其他题库" for b in app.button)
    assert api.get(f"/problem-banks/{target}")["data"]["problem_count"] == 0
    app.button(key=f"bank_edit_{source}_remove_P00").click().run()
    assert api.get(f"/problem-banks/{source}")["data"]["problem_count"] == 2
    assert api.get("/problems/P00")["data"]["id"] == "P00"
    button(app, "← 返回题库主页").click().run()
    button(app, "← 返回我的题库").click().run()
    button(app, "Target").click().run()
    button(app, "删除题库").click().run()
    assert button(app, "确认删除").disabled
    app.checkbox(key=f"bank_delete_confirm_{target}").check().run()
    button(app, "确认删除").click().run()
    assert not app.exception
    assert "bank" not in app.query_params
    assert len(api.get("/problem-banks/")["data"]) == 1
    assert api.get("/problems/P00")["data"]["id"] == "P00"


def test_deleted_problem_is_read_only_and_can_be_removed_in_editor(ui):
    app, api = ui
    source = api.post("/problem-banks/", json={"name": "Source"})["data"]["id"]
    api.post("/problem-banks/", json={"name": "Target"})
    api.post(f"/problem-banks/{source}/problems", json={"problem_ids": ["P00", "P01"]})
    api.client.post("/api/auth/login", json={"username": "admin", "password": "admintestpassword"})
    api.delete("/problems/P00")
    api.client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    app.run()
    button(app, "Source").click().run()
    assert app.button(key=f"bank_{source}_open_P00").disabled
    button(app, "编辑题库").click().run()
    assert not app.checkbox
    app.button(key=f"bank_edit_{source}_remove_P00").click().run()
    assert api.get(f"/problem-banks/{source}")["data"]["problem_count"] == 1
    app.selectbox(key=f"bank_edit_{source}_difficulty").select("简单").run()
    assert not app.checkbox
    assert not app.exception


def test_fully_collected_bank_keeps_add_filters_and_explains_empty_state(ui):
    app, api = ui
    bank = api.post(
        "/problem-banks/",
        json={"name": "全部题目", "problem_ids": [f"P{number:02}" for number in range(12)]},
    )["data"]["id"]
    app.run()
    button(app, "全部题目").click().run()
    button(app, "编辑题库").click().run()
    button(app, "增加题目").click().run()
    assert not app.exception
    assert app.text_input(key=f"bank_add_{bank}_search")
    assert app.selectbox(key=f"bank_add_{bank}_difficulty")
    assert any("当前题目均已收录" in item.value for item in app.markdown)
    assert button(app, "确认增加").disabled
    button(app, "← 返回编辑题库").click().run()
    assert not app.exception
    assert api.get(f"/problem-banks/{bank}")["data"]["problem_count"] == 12


def test_problem_detail_adds_to_owned_bank_without_leaving_or_duplicating(ui):
    app, api = ui
    bank = api.post("/problem-banks/", json={"name": "收藏"})["data"]["id"]
    app.session_state["test_page"] = "catalogue"
    app.run()
    app.button(key="open_problem_P00").click().run()
    assert not app.exception
    app.button(key="detail_bank_add_P00").click().run()
    assert app.query_params["problem"] == ["P00"]
    assert api.get(f"/problem-banks/{bank}")["data"]["problem_count"] == 1
    app.button(key="detail_bank_add_P00").click().run()
    assert api.get(f"/problem-banks/{bank}")["data"]["problem_count"] == 1


def test_private_widgets_cleared_when_identity_changes():
    state = {"bank_draft_new": {"name": "private"}, "bank_selection_problem_list_item_P1": True}
    clear_auth(state)
    assert not any(key.startswith("bank_") for key in state)
    set_auth_user({"id": 2}, state)
    state["bank_draft_new"] = {"name": "another private name"}
    set_auth_user({"id": 3}, state)
    assert "bank_draft_new" not in state
