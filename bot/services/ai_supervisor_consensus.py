"""Multi-provider planning layer for the existing AI Supervisor.

This layer only produces and validates plans. It never executes repository or
runtime changes. Execution remains behind the existing ChangeSet gate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Plan:
    summary: str
    risk: str
    rationale: str
    files: tuple[str, ...]
    requires_confirmation: bool = True


@dataclass(frozen=True)
class Opinion:
    provider: str
    model: str
    plan: Plan | None
    error: str | None = None


_ALLOWED_RISKS = {"low", "medium", "high", "critical"}


class SupervisorConsensus:
    def __init__(self, provider_pool: Any, audit: Any | None = None):
        self.pool = provider_pool
        self.audit = audit

    async def propose(self, request: str, max_agents: int = 3) -> tuple[Plan, tuple[Opinion, ...]]:
        candidates = self._candidates(max_agents)
        opinions: list[Opinion] = []
        for provider, model in candidates:
            try:
                raw = await self.pool.chat(
                    provider,
                    model,
                    self._system_prompt(),
                    request,
                )
                opinions.append(Opinion(provider, model, self._parse(raw)))
            except Exception as exc:
                opinions.append(Opinion(provider, model, None, type(exc).__name__))

        valid = [op.plan for op in opinions if op.plan is not None]
        if not valid:
            raise RuntimeError("No AI provider returned a valid plan")
        selected = self._select(valid)
        if self.audit:
            self.audit.record(
                "ai_consensus_plan",
                providers=[op.provider for op in opinions],
                risk=selected.risk,
                files=list(selected.files),
            )
        return selected, tuple(opinions)

    def _candidates(self, limit: int) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for provider, info in self.pool.status().items():
            if info.get("configured") and info.get("healthy", True):
                models = info.get("models") or []
                if models:
                    result.append((provider, models[0]))
            if len(result) >= max(1, limit):
                break
        return result

    @staticmethod
    def _system_prompt() -> str:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "risk": {"type": "string", "enum": sorted(_ALLOWED_RISKS)},
                "rationale": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}},
                "requires_confirmation": {"type": "boolean"},
            },
            "required": ["summary", "risk", "rationale", "files", "requires_confirmation"],
        }
        return (
            "You are a senior software engineer reviewing XFI CONNECT. "
            "Return ONLY JSON matching this schema. Never propose shell commands, secrets, "
            "deployment credentials, or direct execution. Every change requires explicit admin confirmation.\n"
            + json.dumps(schema, ensure_ascii=False)
        )

    @staticmethod
    def _parse(raw: str) -> Plan:
        data = json.loads(raw)
        required = {"summary", "risk", "rationale", "files", "requires_confirmation"}
        if set(data) != required:
            raise ValueError("Invalid plan schema")
        if data["risk"] not in _ALLOWED_RISKS:
            raise ValueError("Invalid risk")
        if not isinstance(data["files"], list) or not all(isinstance(x, str) for x in data["files"]):
            raise ValueError("Invalid file list")
        return Plan(
            str(data["summary"]),
            data["risk"],
            str(data["rationale"]),
            tuple(data["files"]),
            True,
        )

    @staticmethod
    def _select(plans: list[Plan]) -> Plan:
        # Conservative policy: never downgrade risk. Prefer fewer files when risk ties.
        rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        return min(plans, key=lambda p: (rank[p.risk], len(p.files)))
