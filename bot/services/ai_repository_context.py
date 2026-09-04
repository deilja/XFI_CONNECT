"""Build bounded, secret-aware repository context for the admin AI."""
from __future__ import annotations

from pathlib import Path

DEFAULT_EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "data", "logs"}
DEFAULT_EXCLUDED_NAMES = {".env", ".env.local", ".env.production"}
DEFAULT_EXCLUDED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".sqlite", ".db"}


class RepositoryContext:
    def __init__(self, root: str | Path, max_files: int = 80, max_file_bytes: int = 80_000):
        self.root = Path(root).resolve()
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes

    def _allowed(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if any(part in DEFAULT_EXCLUDED_DIRS for part in path.relative_to(self.root).parts):
            return False
        if path.name in DEFAULT_EXCLUDED_NAMES or path.suffix.lower() in DEFAULT_EXCLUDED_SUFFIXES:
            return False
        return path.suffix.lower() in {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}

    def collect(self, query: str = "") -> str:
        files = []
        needle = query.lower().strip()
        for path in sorted(self.root.rglob("*")):
            if len(files) >= self.max_files:
                break
            if not self._allowed(path):
                continue
            relative = path.relative_to(self.root).as_posix()
            if needle and needle not in relative.lower():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if len(data) > self.max_file_bytes or b"\x00" in data:
                continue
            files.append(f"===== {relative} =====\n{data.decode('utf-8', errors='replace')}")
        return "\n\n".join(files)


def build_repository_context(root: str | Path, query: str = "") -> str:
    """Return bounded repository contents for an AI planning request."""
    return RepositoryContext(root).collect(query)
