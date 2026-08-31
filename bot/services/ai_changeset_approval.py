"""Immutable approval records for AI-generated ChangeSets."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from bot.services.ai_changeset import ChangeSet


@dataclass(frozen=True)
class ApprovalRecord:
    task_id: str
    changeset_digest: str
    token: str
    approved: bool = False


def changeset_digest(changeset: ChangeSet) -> str:
    payload = changeset.request + "\n" + "\n".join(
        f"{c.path}\0{c.old_sha256}\0{c.new_content}" for c in changeset.changes
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ChangeSetApprovalStore:
    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}

    def issue(self, task_id: str, changeset: ChangeSet) -> ApprovalRecord:
        record = ApprovalRecord(task_id, changeset_digest(changeset), secrets.token_urlsafe(18))
        self._records[task_id] = record
        return record

    def approve(self, task_id: str, token: str, changeset: ChangeSet) -> ApprovalRecord:
        record = self._records.get(task_id)
        if not record or not hmac.compare_digest(record.token, token):
            raise PermissionError("invalid approval token")
        digest = changeset_digest(changeset)
        if not hmac.compare_digest(record.changeset_digest, digest):
            raise PermissionError("changeset changed after approval request")
        approved = ApprovalRecord(record.task_id, record.changeset_digest, record.token, True)
        self._records[task_id] = approved
        return approved

    def is_approved(self, task_id: str, changeset: ChangeSet) -> bool:
        record = self._records.get(task_id)
        return bool(record and record.approved and hmac.compare_digest(record.changeset_digest, changeset_digest(changeset)))
