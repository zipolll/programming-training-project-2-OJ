"""Validate commit subjects against the project's Conventional Commit policy."""

import re
import sys
from pathlib import Path

ALLOWED_TYPES = (
    "build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test"
)
COMMIT_PATTERN = re.compile(
    rf"^(?:{ALLOWED_TYPES})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: .+[^.]$"
)


def is_conventional_commit(subject: str) -> bool:
    """Return whether a one-line commit subject follows the enforced format."""
    return bool(COMMIT_PATTERN.fullmatch(subject.strip()))


def main() -> int:
    """Validate the first line of the commit message file passed by Git."""
    if len(sys.argv) != 2:
        print("Usage: validate_commit_message.py <commit-message-file>")
        return 2

    subject = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()[0]
    if is_conventional_commit(subject):
        return 0

    print("Commit rejected: use Conventional Commits, for example:")
    print("  feat(problems): add problem creation endpoint")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
