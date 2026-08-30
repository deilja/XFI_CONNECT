"""Application-level bridge: supervisor -> ChangeSet -> transaction -> verification."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable

from bot.services.ai_agent import AIAgent
from bot.services.ai_autopilot import AIAutopilot, ChangePlan
from bot.services.ai_changeset import apply, begin, commit, rollback
from bot.services.ai_changeset_parser import parse_changeset
from bot.services.ai_executor import ExecutionResult

logger = logging.getLogger(__name__)
Verifier = Callable[[ChangePlan], Awaitable[bool]]


class AutopilotEngine:
    def __init__(self, autopilot: AIAutopilot, project_root: str | Path, verifier: Verifier | None = None):
        self.autopilot = autopilot
        self.project_root = Path(project_root).resolve()
        self.verifier = verifier

    async def build_changeset(self, request: str) -> tuple[str, ChangePlan, object]:
        token, plan = await self.autopilot.prepare(request)
        prompt = (
            "Подготовь ChangeSet для уже согласованного плана. Ответ ТОЛЬКО JSON: "
            "{rationale:string, changes:[{path:string, old_sha256:string, new_content:string}]}. "
            "Используй только необходимые исходные файлы проекта. Не меняй секреты, CI/CD, "
            "deployment или зависимости. Не добавляй команды shell.\nПлан: " + plan.summary
        )
        raw = await self.autopilot.agent.chat(prompt, role="changeset generator")
        proposed = parse_changeset(raw, self.project_root, request)
        return token, plan, proposed.changeset

    async def execute_confirmed(self, token: str, changeset, plan: ChangePlan) -> ExecutionResult:
        authorized = self.autopilot.authorize(token)
        if authorized is not plan:
            plan = authorized
        tx = begin(changeset, self.project_root)
        try:
            apply(tx, changeset)
            verified = await self._verify(plan)
            if not verified:
                rollback(tx)
                return ExecutionResult("changeset", False, "Verification failed; complete rollback finished")
            commit(tx)
            self.autopilot.pending.pop(token, None)
            return ExecutionResult("changeset", True, "Changes applied and all verification checks passed")
        except Exception:
            logger.exception("AI ChangeSet failed; rolling back")
            try:
                rollback(tx)
            finally:
                self.autopilot.pending.pop(token, None)
            raise

    async def _verify(self, plan: ChangePlan) -> bool:
        if self.verifier is not None:
            return bool(await self.verifier(plan))
        # Default to the application-owned production verifier.
        from bot.services.ai_runtime_verifier import build_production_verifier
        verifier, _pipeline = await build_production_verifier(self.project_root)
        return bool(await verifier(plan))
