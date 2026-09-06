"""Deterministic preview data, with no real account or backend writes."""

import streamlit as st

PROBLEM = {
    "id": "hotword-ranking",
    "title": "热搜词排行榜",
    "description": "统计词语出现次数。",
    "input_description": "输入词语列表",
    "output_description": "输出排行榜",
    "constraints": "1 ≤ n ≤ 100000",
    "difficulty": "中等",
    "problem_type": "基础编程",
    "tags": ["模拟", "字符串", "哈希表"],
    "time_limit": 3.0,
    "memory_limit": 128,
    "source": "训练营",
    "author": "teacher",
    "hint": "使用哈希表",
    "samples": [{"input": "hello hello", "output": "hello 2"}],
    "testcases": [{"input": "oj oj", "output": "oj 2"}],
}


class PreviewApi:
    base_url = "http://offline-ui-fixture"

    def get(self, path, params=None):
        st.session_state["fixture_last_get"] = (path, params)
        if path.startswith("/problem-banks/"):
            banks = [
                {
                    "id": 1,
                    "name": "基础算法练习",
                    "description": "从数组、字符串开始，逐步熟悉常见算法。",
                    "problem_count": 1,
                    "problems": [PROBLEM],
                },
                {
                    "id": 2,
                    "name": "每周复习",
                    "description": "记录值得再次挑战的题目。",
                    "problem_count": 0,
                    "problems": [],
                },
            ]
            data = banks if path == "/problem-banks/" else banks[int(path.rsplit("/", 1)[1]) - 1]
        elif path == "/problems/":
            data = [PROBLEM, {**PROBLEM, "id": "sum", "title": "两数之和", "tags": []}]
        elif path.startswith("/problems/"):
            data = PROBLEM
        elif path == "/languages/":
            data = {"name": ["python", "cpp"]}
        elif path == "/users/":
            data = {
                "total": 3,
                "users": [
                    {
                        "user_id": i,
                        "username": name,
                        "role": role,
                        "join_time": "2026-09-02",
                        "submit_count": 2,
                        "resolve_count": 1,
                    }
                    for i, name, role in [
                        (1, "admin", "admin"),
                        (2, "ZFX", "user"),
                        (3, "user2", "banned"),
                    ]
                ],
            }
        elif path == "/logs/audit/":
            records = [
                {"action": "update_user_role", "changes": {"before": "user", "after": "admin"}},
                {"action": "view_logs", "changes": {}},
                {"action": "future_action", "changes": {"custom": "<script>alert(1)</script>"}},
            ]
            data = {
                "total": 23,
                "logs": [
                    {
                        "created_at": "2026-09-04T12:42:15.588163+00:00",
                        "user_id": 1,
                        "username": "admin",
                        "target_type": "submission",
                        "target_id": "2",
                        "problem_id": "hotword-ranking",
                        "success": i != 2,
                        "status": 200 if i != 2 else 403,
                        **entry,
                    }
                    for i, entry in enumerate(records)
                ],
            }
        elif path.endswith("/log"):
            data = {
                "details": [
                    {
                        "id": i,
                        "result": ["AC", "WA", "TLE", "CE", "MLE", "RE", "UNK"][i - 1],
                        "time": 0.093,
                        "memory": 22.02,
                        "error_summary": "",
                    }
                    for i in range(1, 8)
                ]
            }
        elif path == "/submissions/":
            data = {
                "total": 3,
                "submissions": [
                    {"submission_id": i, "status": "success", "score": score, "counts": 100}
                    for i, score in [(3, 100), (2, 0), (1, 40)]
                ],
            }
        elif path.startswith("/submissions/"):
            data = {
                "submission_id": int(path.rsplit("/", 1)[1]),
                "status": "success",
                "score": 0,
                "counts": 100,
                "language": "cpp",
                "code": "#include <iostream>\nint main() { std::cout << 42; }",
                "result": "CE",
                "compile_info": {"result": "error", "message": "compiler: missing ;"},
            }
        elif path == "/agent/config":
            data = {
                "encryption_configured": True,
                "has_api_key": True,
                "model_name": "test-model",
                "provider_url": "https://example.test/v1",
            }
        elif path == "/agent/tasks":
            data = []
        else:
            raise AssertionError(f"Unexpected fixture request: {path}")
        return {"data": data}

    def post(self, path, json=None):
        st.session_state["fixture_saved"] = (path, json)
        return {
            "data": {
                "name": (json or {}).get("name"),
                "submission_id": 4,
                "status": "pending",
                "task_id": "fixture-task",
            }
        }

    def put(self, path, json=None):
        return self.post(path, json)
