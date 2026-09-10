"""Silent archetype matching that upgrades common algorithm tasks to strong data.

Complexity-separation problems (range queries, membership bookkeeping, queue
simulation, interval scanning) live or die by their data scale: without
maximum-scale cases a brute-force solution passes and the exercise tests
nothing. This module recognizes such tasks from the authoring request alone
and hands the model a battle-tested data-strength profile — concrete scales,
the brute force to reject, and the output budget — while the UI stays generic.
"""

import re
from typing import Any

from backend.app.modules.agent.models import AuthoringRequest

# CJK keywords match as substrings; ASCII keywords match on word boundaries so
# "set" does not fire inside "settle".
_ARCHETYPE_SPECS: dict[str, dict[str, Any]] = {
    "range_query": {
        "keywords": ["前缀和", "区间和", "区间查询", "prefix sum", "prefix-sum"],
        "guidance": {
            "task_shape": (
                "array/daily counts plus many range-sum queries answered from "
                "precomputed prefix sums"
            ),
            "suggested_constraints": (
                "n <= 2*10^5 elements with values 0..1000, q <= 2500 queries with "
                "1 <= l <= r <= n"
            ),
            "reference_budget": (
                "reference preprocesses prefix sums once, O(n+q); in Python it must "
                "finish in well under half of time_limit (suggest 3.0s) on max cases"
            ),
            "brute_force": (
                "the wrong solution recomputes each query by scanning the range: "
                "q*n >= 5*10^8 elementary operations on max cases and must TLE "
                "while passing small hand-written cases"
            ),
            "output_budget": (
                "one line per query, q <= 2500 lines, safely inside the default "
                "65536-byte capture limit; do not raise output_limit_bytes"
            ),
            "stress_cases": (
                "generator cases: random max (n=2*10^5, q=2500), query-heavy with "
                "repeated and full-range queries, and a medium random case"
            ),
        },
    },
    "membership_bookkeeping": {
        "keywords": [
            "集合",
            "字典",
            "哈希",
            "预约",
            "重复入场",
            "无预约",
            "去重",
            "set",
            "dict",
            "hash",
        ],
        "guidance": {
            "task_shape": (
                "a large eligible/id list plus a request stream; each request is "
                "classified (allowed / duplicate / not eligible) via set or dict "
                "state"
            ),
            "suggested_constraints": (
                "m <= 1*10^5 eligible ids, q <= 4000 requests, ids are integers "
                "in 1..10^9, requests arrive in order"
            ),
            "reference_budget": (
                "reference keeps eligible ids and seen ids in set/dict, O(m+q); in "
                "Python well under half of time_limit (suggest 3.0s)"
            ),
            "brute_force": (
                "the wrong solution scans the whole eligible list for every "
                "request: q*m >= 4*10^8 operations on max cases and must TLE"
            ),
            "output_budget": (
                "one short status line per request, q <= 4000 lines; keep answers "
                "like OK/DUPLICATE/NO so output stays under the default limit"
            ),
            "stress_cases": (
                "generator cases: max random with all three statuses present, "
                "duplicate-heavy (same ids requesting repeatedly), and not-eligible "
                "heavy"
            ),
        },
    },
    "queue_simulation": {
        "keywords": [
            "asyncio",
            "优先队列",
            "调度",
            "并发数",
            "执行单元",
            "完成时间",
            "priority queue",
            "heap",
        ],
        "guidance": {
            "task_shape": (
                "tasks arriving over time served by at most k concurrent executors; "
                "free executors take tasks in arrival order; simulate with a min-heap "
                "of executor finish times — no real waiting or system scheduling"
            ),
            "suggested_constraints": (
                "n <= 1*10^5 tasks, k <= 1000 executors, arrival times strictly "
                "increasing, durations 1..10^6"
            ),
            "reference_budget": (
                "reference uses heapq, O(n log k); in Python well under half of "
                "time_limit (suggest 4.0s) on max cases"
            ),
            "brute_force": (
                "the wrong solution iterates over every executor (or every pending "
                "task) for every assignment: n*k >= 10^8 operations on max cases and "
                "must TLE; also reject per-tick simulation over the whole time span"
            ),
            "output_budget": (
                "the task outputs one completion time per task, so set "
                "problem.output_limit_bytes = 4194304 and keep every case's output "
                "(n lines) below it"
            ),
            "stress_cases": (
                "generator cases: max random, burst arrivals (many tasks at the "
                "same instant), and long durations keeping all k executors busy"
            ),
        },
    },
    "interval_scan": {
        "keywords": [
            "扫描线",
            "最大并发",
            "并发线程",
            "左闭右开",
            "事件排序",
            "重叠区间",
            "sweep",
            "overlap",
        ],
        "guidance": {
            "task_shape": (
                "n intervals [start, end); report the maximum number of overlapping "
                "intervals and the earliest moment it occurs, via event sorting or "
                "a sweep line"
            ),
            "suggested_constraints": (
                "n <= 1*10^5 intervals, start < end, times 1..10^9"
            ),
            "reference_budget": (
                "reference sorts 2n events and scans once, O(n log n); in Python "
                "well under half of time_limit (suggest 3.0s)"
            ),
            "brute_force": (
                "the wrong solution compares every pair of intervals (n^2 >= 10^10 "
                "ops) or simulates every distinct timestamp; both must TLE on max "
                "cases"
            ),
            "output_budget": (
                "exactly two lines of output; never raise output_limit_bytes"
            ),
            "stress_cases": (
                "generator cases: max random, many shared endpoints / nested "
                "intervals, and a case where the maximum ties and the earliest "
                "moment matters"
            ),
        },
    },
}

_ASCII_KEYWORD = re.compile(r"[a-z0-9]", re.IGNORECASE)


def _request_text(request: AuthoringRequest) -> str:
    parts = [
        request.prompt,
        request.expected_algorithm,
        request.data_scale,
        request.background_preference,
        request.additional_requirements,
        " ".join(request.required_knowledge),
    ]
    return " ".join(part for part in parts if part).casefold()


def _keyword_present(keyword: str, text: str) -> bool:
    if not keyword:
        return False
    if _ASCII_KEYWORD.search(keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text


def detect_archetype(request: AuthoringRequest) -> str | None:
    """Return the matching archetype name, or None when no strong match."""
    text = _request_text(request)
    best_name: str | None = None
    best_hits = 0
    for name, spec in _ARCHETYPE_SPECS.items():
        hits = sum(1 for keyword in spec["keywords"] if _keyword_present(keyword, text))
        if hits > best_hits:
            best_name, best_hits = name, hits
    return best_name if best_hits >= 1 else None


def archetype_guidance(name: str | None) -> dict[str, Any] | None:
    if name is None:
        return None
    spec = _ARCHETYPE_SPECS.get(name)
    return spec["guidance"] if spec else None


__all__ = ["archetype_guidance", "detect_archetype"]
