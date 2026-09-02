"""Conventional Commit validator tests."""

from scripts.validate_commit_message import is_conventional_commit


def test_accepts_conventional_commit() -> None:
    assert is_conventional_commit("chore: scaffold application framework")
    assert is_conventional_commit("feat(problems)!: replace problem schema")


def test_rejects_non_conventional_commit() -> None:
    assert not is_conventional_commit("initial files")
    assert not is_conventional_commit("Feat: uppercase type is invalid")
