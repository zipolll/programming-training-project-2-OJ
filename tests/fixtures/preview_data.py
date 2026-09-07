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

    def get_health(self):
        return self.get("/health")

    def get(self, path, params=None):
        st.session_state["fixture_last_get"] = (path, params)
        if path == "/health":
            data = {"status": "ok"}
        elif path.startswith("/users/") and path != "/users/":
            data = {
                "username": "训练者",
                "role": st.session_state["auth_user"]["role"],
                "join_time": "2026-09-02",
                "submit_count": 12,
                "resolve_count": 5,
            }
        elif path.startswith("/problem-banks/"):
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
            if st.session_state.get("fixture_rich"):
                banks.extend(
                    {
                        "id": index,
                        "name": name,
                        "description": description,
                        "problem_count": count,
                        "problems": [PROBLEM] if count else [],
                    }
                    for index, name, description, count in (
                        (3, "字符串与模式匹配", "从字符统计到模式匹配，集中练习字符串处理。", 12),
                        (
                            4,
                            "图论与动态规划专题复习题库",
                            "这里收录需要反复理解的状态转移、最短路径和图遍历题目。描述可以比较长，列表中保持两行，进入题库后可以阅读全部内容。",
                            24,
                        ),
                        (5, "考前回顾", "重新梳理边界条件与复杂度分析。", 8),
                        (6, "待整理", "", 0),
                    )
                )
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
        if st.session_state.get("fixture_rich"):
            if path == "/problems/":
                data = [
                    *data,
                    *[
                        {**PROBLEM, "id": pid, "title": title, "tags": tags, "difficulty": level}
                        for pid, title, tags, level in (
                            ("brackets", "括号的秩序", ["栈", "字符串"], "中等"),
                            (
                                "hanoi_kth_move",
                                "汉诺塔的第 k 步",
                                ["recursion", "divide_and_conquer", "math"],
                                "简单",
                            ),
                            ("prefix_sum", "区间求和", ["前缀和", "数组"], "入门"),
                            (
                                "long_problem_identifier_for_responsive_layout_2026",
                                "带有较长标题的最短路径与状态压缩综合训练题目",
                                ["图论", "最短路径", "状态压缩动态规划"],
                                "困难",
                            ),
                        )
                    ],
                ]
            elif path.startswith("/problems/"):
                data = {
                    **data,
                    "description": (
                        "给定一组用户搜索词，请统计每个词语出现的次数，"
                        "并按出现次数从高到低输出排行榜。\n\n"
                        "如果两个词语出现次数相同，则按照字典序排列。"
                        "你需要选择合适的数据结构，在给定的时间与内存限制内处理全部输入。"
                    ),
                    "input_description": (
                        "第一行是整数 n，表示搜索词的数量。"
                        "接下来 n 行，每行包含一个仅由小写英文字母组成的词语。"
                    ),
                    "output_description": (
                        "按要求输出排行榜，每行包含一个词语和它的出现次数，中间以空格分隔。"
                    ),
                    "samples": [
                        {
                            "input": "5\napple\npear\napple\nbanana\npear",
                            "output": "apple 2\npear 2\nbanana 1",
                        }
                    ],
                }
                if path.endswith("long_problem_identifier_for_responsive_layout_2026"):
                    data = {
                        **data,
                        "id": path.rsplit("/", 1)[1],
                        "title": "带有较长标题的最短路径与状态压缩综合训练题目",
                    }
        if path == "/problem-banks/" and st.query_params.get("fixture_banks") == "empty":
            data = []
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
