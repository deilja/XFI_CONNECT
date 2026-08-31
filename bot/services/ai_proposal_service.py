"""Build structured AI change proposals from repository context.

AI produces JSON only; this service validates it before it reaches ChangeSetBridge.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from bot.services.ai_agent import AIAgent
from bot.services.ai_change_proposal import parse_change_proposal
from bot.services.ai_repository_context import build_repository_context
from bot.services.ai_changeset_bridge import ProposedChange


@dataclass(frozen=True)
class AIProposal:
    summary: str
    changes: list[ProposedChange]


class AIProposalService:
    def __init__(self, agent: AIAgent, project_root: str):
        self.agent = agent
        self.project_root = project_root

    async def propose(self, request: str) -> AIProposal:
        context = build_repository_context(self.project_root, request)
        prompt = (
            "Проанализируй задачу администратора и контекст репозитория. "
            "Верни ТОЛЬКО JSON без markdown. Не придумывай файлы. "
            "Изменяй только необходимые файлы. Формат: "
            '{"summary":"...","changes":[{"path":"...","new_content":"..."}]}\n\n'
            f"ЗАДАЧА:\n{request}\n\nКОНТЕКСТ:\n{context}"
        )
        raw = await self.agent.chat(prompt, role="repository change planner", task_type="code_change")
        data: Any = json.loads(raw)
        proposal = parse_change_proposal(data)
        return AIProposal(
            summary=proposal.summary,
            changes=[ProposedChange(c.path, c.new_content) for c in proposal.changes],
        )
