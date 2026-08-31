"""Bridge between AI-generated proposals and the strict ChangeSet engine."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from bot.services.ai_changeset import ChangeSet, ChangeSetError, FileChange, Transaction, begin, apply, commit, rollback, validate_changeset


@dataclass(frozen=True)
class ProposedChange:
    path: str
    new_content: str


class ChangeSetBridge:
    """Build and apply changes only against expected file hashes."""

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()

    def build(self, request: str, proposed: list[ProposedChange]) -> ChangeSet:
        changes: list[FileChange] = []
        for item in proposed:
            path = (self.root / item.path).resolve()
            try:
                path.relative_to(self.root)
            except ValueError as exc:
                raise ChangeSetError(f"Path escapes project root: {item.path!r}") from exc
            current = path.read_bytes() if path.exists() else None
            old_sha = hashlib.sha256(current).hexdigest() if current is not None else "MISSING"
            changes.append(FileChange(item.path, old_sha, item.new_content))
        result = ChangeSet(request, tuple(changes))
        validate_changeset(result, self.root)
        return result

    def preview(self, changeset: ChangeSet) -> str:
        validate_changeset(changeset, self.root)
        lines = [f"ChangeSet: {changeset.request}"]
        for change in changeset.changes:
            lines.append(f"- {change.path} ({change.old_sha256[:12]} -> proposed)")
        return "\n".join(lines)

    def start(self, changeset: ChangeSet) -> Transaction:
        return begin(changeset, self.root)

    def apply(self, transaction: Transaction, changeset: ChangeSet) -> None:
        apply(transaction, changeset)

    def verify_and_commit(self, transaction: Transaction, changeset: ChangeSet, verified: bool) -> None:
        if verified:
            commit(transaction)
        else:
            rollback(transaction)
            raise ChangeSetError("Verification failed; changes rolled back")
