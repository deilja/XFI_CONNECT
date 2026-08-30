"""Central safety policy for AI-proposed source changes."""
from __future__ import annotations

PROTECTED_PREFIXES = (
    ".github/workflows/",
    "deploy/",
    "systemd/",
)
PROTECTED_FILES = {
    ".env", ".env.local", ".env.production",
    "pyproject.toml", "requirements.txt",
}
MAX_FILES = 25


def validate_change_paths(paths: list[str]) -> None:
    if len(paths) == 0:
        raise ValueError("ChangeSet is empty")
    if len(paths) > MAX_FILES:
        raise ValueError(f"Too many files in one AI ChangeSet: {len(paths)} > {MAX_FILES}")
    for path in paths:
        normalized = path.replace("\\", "/").lstrip("./")
        if normalized in PROTECTED_FILES or normalized.startswith(PROTECTED_PREFIXES):
            raise PermissionError(f"Protected path requires a separate reviewed change: {path}")
