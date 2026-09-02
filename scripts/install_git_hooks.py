"""Configure this repository to use its version-controlled Git hooks."""

import subprocess
from pathlib import Path


def main() -> None:
    """Point core.hooksPath at the repository's hook directory."""
    repository_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=repository_root,
        check=True,
    )
    print("Git hooks installed: Conventional Commits are now enforced.")


if __name__ == "__main__":
    main()
