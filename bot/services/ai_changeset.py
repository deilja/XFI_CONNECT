"""Strict file ChangeSet engine for the unified AI supervisor.

The model may propose text changes, but this module validates paths and the
expected content hash before touching a file. It creates a reversible local
backup and can restore every changed file when verification fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ChangeSetError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileChange:
    path: str
    old_sha256: str
    new_content: str


@dataclass(frozen=True)
class ChangeSet:
    request: str
    changes: tuple[FileChange, ...]


@dataclass
class Transaction:
    root: Path
    backup_dir: Path
    originals: dict[str, bytes | None]
    applied: bool = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute() or "\x00" in relative:
        raise ChangeSetError(f"Invalid relative path: {relative!r}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ChangeSetError(f"Path escapes project root: {relative!r}") from exc
    if candidate.is_symlink():
        raise ChangeSetError(f"Symlink modification is forbidden: {relative!r}")
    return candidate


def validate_changeset(changeset: ChangeSet, root: str | Path) -> None:
    project = Path(root).resolve()
    seen: set[str] = set()
    for change in changeset.changes:
        if change.path in seen:
            raise ChangeSetError(f"Duplicate path: {change.path}")
        seen.add(change.path)
        if len(change.new_content.encode("utf-8")) > 2_000_000:
            raise ChangeSetError(f"File change too large: {change.path}")
        path = _safe_path(project, change.path)
        current = path.read_bytes() if path.exists() else None
        actual = _sha256(current) if current is not None else "MISSING"
        if actual.lower() != change.old_sha256.lower():
            raise ChangeSetError(
                f"Content hash mismatch for {change.path}: expected {change.old_sha256}, got {actual}"
            )
        if path.name in {".env", ".env.local", ".env.production"} or path.suffix in {".pem", ".key"}:
            raise ChangeSetError(f"Sensitive file is not editable by AI: {change.path}")


def begin(changeset: ChangeSet, root: str | Path) -> Transaction:
    project = Path(root).resolve()
    validate_changeset(changeset, project)
    backup = Path(tempfile.mkdtemp(prefix=".xfi-ai-change-", dir=str(project)))
    originals: dict[str, bytes | None] = {}
    try:
        for change in changeset.changes:
            path = _safe_path(project, change.path)
            originals[change.path] = path.read_bytes() if path.exists() else None
            if originals[change.path] is not None:
                target = backup / change.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(originals[change.path])
        return Transaction(project, backup, originals)
    except Exception:
        import shutil
        shutil.rmtree(backup, ignore_errors=True)
        raise


def apply(transaction: Transaction, changeset: ChangeSet) -> None:
    if transaction.applied:
        raise ChangeSetError("Transaction already applied")
    validate_changeset(changeset, transaction.root)
    for change in changeset.changes:
        path = _safe_path(transaction.root, change.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".xfi-ai-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(change.new_content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
    transaction.applied = True


def rollback(transaction: Transaction) -> None:
    import shutil
    for relative, original in transaction.originals.items():
        path = _safe_path(transaction.root, relative)
        if original is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".xfi-ai-rollback-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
    transaction.applied = False
    shutil.rmtree(transaction.backup_dir, ignore_errors=True)


def commit(transaction: Transaction) -> None:
    import shutil
    if not transaction.applied:
        raise ChangeSetError("Nothing to commit")
    shutil.rmtree(transaction.backup_dir, ignore_errors=True)
    transaction.applied = False
