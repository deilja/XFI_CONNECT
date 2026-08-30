"""Single safe entry point from administrator request to verified ChangeSet.

The supervisor may propose work, but only the existing ChangeSet transaction
engine can mutate files. Execution always requires explicit confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class SupervisorDecision:
    request: str
    summary: str
    rationale: str
    risk: str
    requires_confirmation: bool
    changeset_payload: str
    providers_used: tuple[str, ...]


class AISupervisorPipeline:
    def __init__(
        self,
        consensus: Any,
        changeset_builder: Callable[[str, str], Awaitable[Any]],
        executor: Callable[[Any], Awaitable[Any]],
        audit: Any | None = None,
    ) -> None:
        self.consensus = consensus
        self.changeset_builder = changeset_builder
        self.executor = executor
        self.audit = audit
        self.pending: dict[str, Any] = {}

    async def propose(self, request: str) -> SupervisorDecision:
        request = request.strip()
        if not request:
            raise ValueError("Пустой запрос администратора")

        result = await self.consensus.plan(request)
        plan = getattr(result, "plan", result)
        summary = str(getattr(plan, "summary", ""))
        rationale = str(getattr(plan, "rationale", ""))
        risk = str(getattr(plan, "risk", "medium")).lower()
        confirmation = risk in {"high", "critical"} or bool(getattr(plan, "requires_confirmation", True))

        payload = await self.changeset_builder(request, summary)
        token = self._token(request, summary)
        self.pending[token] = payload
        decision = SupervisorDecision(
            request=request,
            summary=summary,
            rationale=rationale,
            risk=risk,
            requires_confirmation=confirmation,
            changeset_payload=token,
            providers_used=tuple(getattr(result, "providers_used", ())),
        )
        if self.audit:
            self.audit.record("supervisor_proposal", request=request, risk=risk, token=token, providers=decision.providers_used)
        return decision

    async def confirm(self, token: str) -> Any:
        payload = self.pending.pop(token, None)
        if payload is None:
            raise ValueError("Proposal expired or already executed")
        if self.audit:
            self.audit.record("supervisor_confirm", token=token)
        return await self.executor(payload)

    def reject(self, token: str) -> None:
        self.pending.pop(token, None)
        if self.audit:
            self.audit.record("supervisor_reject", token=token)

    @staticmethod
    def _token(request: str, summary: str) -> str:
        import hashlib
        return hashlib.sha256(f"{request}\0{summary}".encode()).hexdigest()[:24]
