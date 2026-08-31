"""Strict parser for AI change proposals.

Expected format is JSON only. No shell commands are accepted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from bot.services.ai_changeset_bridge import ProposedChange


@dataclass(frozen=True)
class ChangeProposal:
    summary: str
    changes: tuple[ProposedChange, ...]


def parse_change_proposal(raw: str) -> ChangeProposal:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AI proposal must be valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
        raise ValueError("Invalid AI proposal structure")
    summary = str(payload.get("summary", "")).strip()
    if not summary or len(summary) > 2000:
        raise ValueError("Invalid proposal summary")
    changes: list[ProposedChange] = []
    for item in payload["changes"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("new_content"), str):
            raise ValueError("Invalid change entry")
        if len(item["path"]) > 500 or len(item["new_content"]) > 500_000:
            raise ValueError("Change entry exceeds limits")
        changes.append(ProposedChange(item["path"], item["new_content"]))
    if not changes or len(changes) > 30:
        raise ValueError("Invalid number of changes")
    return ChangeProposal(summary, tuple(changes))
