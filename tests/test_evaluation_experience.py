"""Submission-source privacy, CE compatibility and presentation regressions."""

from types import SimpleNamespace

import pytest

from backend.app.modules.judge.models import TestcaseStatus as Verdict
from backend.app.modules.logs.service import evaluation_log_data
from backend.app.modules.submissions.models import SubmissionStatus
from backend.app.modules.submissions.service import submission_detail
from frontend.components.code_editor import code_language
from frontend.components.ui import status_tone
from frontend.pages.audit import _audit_time_text


def submission(**changes):
    values = dict(submission_id=2, status=SubmissionStatus.SUCCESS, language="cpp",
                  code="int main() {}", result=Verdict.CE, score=0, counts=30,
                  compile_info="compile error", stderr="")
    return SimpleNamespace(**(values | changes))


@pytest.mark.parametrize("status", list(SubmissionStatus))
def test_source_and_language_available_in_every_lifecycle_state(status):
    result = submission_detail(submission(status=status))
    assert result["code"] == "int main() {}"
    assert result["language"] == "cpp"
    assert result["result"] == "CE"


def test_legacy_ce_uses_stored_total_without_writing_or_loading_problem():
    result = evaluation_log_data(submission(), [])
    assert [item["id"] for item in result["details"]] == [1, 2, 3]
    assert all(item["result"] == "CE" for item in result["details"])
    assert all(item["error_summary"] == "编译失败，未运行" for item in result["details"])
    assert result["score"] == 0


@pytest.mark.parametrize("verdict", [Verdict.WA, Verdict.UNK, Verdict.AC, None])
def test_empty_non_ce_log_is_not_fabricated(verdict):
    assert evaluation_log_data(submission(result=verdict), [])["details"] == []


@pytest.mark.parametrize("status", [SubmissionStatus.PENDING, SubmissionStatus.ERROR])
def test_nonterminal_and_internal_errors_do_not_generate_ce_cases(status):
    assert evaluation_log_data(submission(status=status), [])["details"] == []


@pytest.mark.parametrize("verdict,tone", [("AC", "green"), ("WA", "red"), ("TLE", "yellow"),
    ("MLE", "yellow"), ("CE", "blue"), ("RE", "orange"), ("UNK", "gray")])
def test_shared_verdict_palette(verdict, tone):
    assert status_tone(verdict) == tone


@pytest.mark.parametrize("language,mode", [("python", "python"), ("cpp", "cpp"),
    ("C++17", "cpp"), ("Python3", "python"), ("custom", None)])
def test_source_highlighting(language, mode):
    assert code_language(language) == mode


def test_audit_time_beijing_date_rollover_and_invalid_values():
    assert _audit_time_text("2026-09-05T18:01:02.345Z") == "2026-09-06\n02:01:02"
    assert _audit_time_text("2026-09-05T18:01:02+08:00") == "2026-09-05\n18:01:02"
    assert _audit_time_text(None) == "—"
    assert _audit_time_text("bad timestamp") == "bad timestamp"


def test_editor_submits_atomic_event_once_and_not_widget_language(monkeypatch):
    from frontend.components import code_editor

    event = {"code": "print('最后一字')\n", "language": "python", "event_id": "one-event"}
    monkeypatch.setattr(code_editor.st, "session_state", {})
    monkeypatch.setattr(code_editor.st, "selectbox", lambda *a, **kw: "cpp")
    monkeypatch.setattr(code_editor.st, "rerun", lambda: None)
    monkeypatch.setattr(code_editor, "restore_widget", lambda *a, **kw: None)
    monkeypatch.setattr(code_editor, "current_user", lambda: {"id": 1})
    monkeypatch.setattr(code_editor, "_component", lambda: lambda **kw: SimpleNamespace(
        submission=event
    ))
    calls, opened = [], []

    def post(path, json):
        calls.append((path, json))
        return {"data": {"submission_id": 9}}

    monkeypatch.setattr(code_editor, "open_submission", opened.append)
    api = SimpleNamespace(post=post)
    for _ in range(2):
        code_editor.render_code_submission(api, "P1", ["python", "cpp"], key="test")
    assert calls == [("/submissions/", {"problem_id": "P1", "language": "python",
                                       "code": "print('最后一字')\n"})]
    assert opened == ["9"]
