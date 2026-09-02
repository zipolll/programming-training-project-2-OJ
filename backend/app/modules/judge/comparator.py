"""Course-compatible UTF-8 output normalization and comparison."""


class OutputDecodeError(ValueError):
    """Raised when program output is not valid UTF-8."""


def decode_output(output: bytes) -> str:
    try:
        return output.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OutputDecodeError("program output is not valid UTF-8") from exc


def normalize_output(output: str) -> str:
    """Ignore trailing whitespace per line and trailing newline-only lines."""
    normalized_newlines = output.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized_newlines.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def outputs_match(actual: str, expected: str) -> bool:
    return normalize_output(actual) == normalize_output(expected)
