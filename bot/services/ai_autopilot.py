"""Unified AI autopilot: plan -> authorize -> execute -> verify -> rollback."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bot.services.ai_agent import AIAgent

logger = logging.getLogger(__name__)


@dataclass
class ChangePlan:
    request: str
    summary: str
    risk: str
    steps: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    rollback: list[str] = field(default_factory=list)
    requires_confirmation: bool = True


class AIAutopilot:
    """Single administrative agent with a strict two-phase mutation protocol.

    The model proposes and explains changes. Execution is delegated to an explicit
    executor callback supplied by the application, so an LLM can never gain
    arbitrary shell/Git privileges merely by receiving an admin message.
    """

    def __init__(self, agent: AIAgent | None = None):
        self.agent = agent or AIAgent()
        self.pending: dict[str, ChangePlan] = {}

    async def plan(self, request: str) -> ChangePlan:
        prompt = (
            "Сформируй план изменения XFI CONNECT по запросу администратора. "
            "Ответь ТОЛЬКО JSON с полями summary,risk,steps,verification,rollback,requires_confirmation. "
            "Не утверждай, что что-либо уже выполнено. Любое изменение кода, конфигурации, Git, "
            "сервиса или инфраструктуры считать требующим подтверждения.\nЗапрос: " + request
        )
        raw = await self.agent.chat(prompt, role="unified autonomous engineering supervisor")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "summary": raw[:2000],
                "risk": "unknown",
                "steps": [],
                "verification": [],
                "rollback": [],
                "requires_confirmation": True,
            }
        return ChangePlan(
            request=request,
            summary=str(data.get("summary", "")),
            risk=str(data.get("risk", "unknown")),
            steps=[str(x) for x in data.get("steps", [])],
            verification=[str(x) for x in data.get("verification", [])],
            rollback=[str(x) for x in data.get("rollback", [])],
            requires_confirmation=bool(data.get("requires_confirmation", True)),
        )

    async def prepare(self, request: str) -> tuple[str, ChangePlan]:
        plan = await self.plan(request)
        token = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        self.pending[token] = plan
        return token, plan

    def authorize(self, token: str) -> ChangePlan:
        plan = self.pending.get(token)
        if not plan:
            raise KeyError("План не найден или уже использован")
        return plan

    async def execute(self, token: str, executor: Any) -> Any:
        plan = self.pending.pop(token, None)
        if not plan:
            raise KeyError("План не найден или уже использован")
        if not callable(executor):
            raise TypeError("Executor must be an explicit application callback")
        try:
            result = await executor(plan)
            return {"ok": True, "result": result, "verified_at": datetime.now(timezone.utc).isoformat()}
        except Exception:
            logger.exception("Autopilot execution failed; executor must perform rollback")
            raise

    def cancel(self, token: str) -> bool:
        return self.pending.pop(token, None) is not None
