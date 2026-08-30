"""Parse the AI's structured ChangeSet without granting arbitrary execution."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from bot.services.ai_changeset import ChangeSet, FileChange, ChangeSetError
from bot.services.ai_change_policy import validate_change_paths


@dataclass(frozen=True)
class ProposedChangeSet:
    changeset: ChangeSet
    rationale: str


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_changeset(raw: str, root: str | Path, request: str) -> ProposedChangeSet:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChangeSetError("AI response is not valid JSON") from exc
    changes = data.get("changes")
    if not isinstance(changes, list):
        raise ChangeSetError("AI response does not contain a changes list")
    paths: list[str] = []
    result: list[FileChange] = []
    project = Path(root).resolve()
    for item in changes:
        if not isinstance(item, dict):
            raise ChangeSetError("Invalid ChangeSet item")
        path = str(item.get("path", ""))
        old_sha = str(item.get("old_sha256", ""))
        new_content = item.get("new_content")
        if not isinstance(new_content, str):
            raise ChangeSetError(f"new_content must be text: {path}")
        paths.append(path)
        target = (project / path).resolve()
        try:
            target.relative_to(project)
        except ValueError as exc:
            raise ChangeSetError(f"Path escapes project root: {path}") from exc
        actual = sha256_file(target) if target.exists() else "MISSING"
        if old_sha.lower() != actual.lower():
            raise ChangeSetError(f"Stale ChangeSet for {path}: expected {old_sha}, got {actual}")
        result.append(FileChange(path, old_sha, new_content))
    validate_change_paths(paths)
    return ProposedChangeSet(
        ChangeSet(request=request, changes=tuple(result)),
        str(data.get("rationale", "")),
    )
