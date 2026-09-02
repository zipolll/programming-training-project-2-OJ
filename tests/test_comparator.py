"""Unit tests for the course output comparison rules."""

import pytest

from backend.app.modules.judge.comparator import (
    OutputDecodeError,
    decode_output,
    outputs_match,
)


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ("answer", "answer"),
        ("answer   \n", "answer"),
        ("a\t \nb  \n\n", "a\nb"),
        ("你好，世界\n", "你好，世界"),
    ],
)
def test_equivalent_output_matches(actual: str, expected: str) -> None:
    assert outputs_match(actual, expected)


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ("a  b", "a b"),
        ("a\nb", "a"),
        ("a\n\nb", "a\nb"),
        ("a\tb", "a b"),
    ],
)
def test_meaningful_whitespace_difference_does_not_match(actual: str, expected: str) -> None:
    assert not outputs_match(actual, expected)


def test_invalid_utf8_is_rejected() -> None:
    with pytest.raises(OutputDecodeError, match="UTF-8"):
        decode_output(b"\xff")
