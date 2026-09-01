"""High-level pipeline used by Telegram handlers.

It deliberately stops at approval: preparing a proposal never mutates files.
"""
from __future__ import annotations

from bot.services.ai_admin_workflow import AIAdminWorkflow, PendingChange
from bot.services.ai_proposal_service import AIProposalService


class AIAdminPipeline:
    def __init__(self, proposal_service: AIProposalService, workflow: AIAdminWorkflow):
        self.proposal_service = proposal_service
        self.workflow = workflow

    async def prepare(self, task_id: str, request: str) -> PendingChange:
        proposal = await self.proposal_service.propose(request)
        return self.workflow.prepare(task_id, proposal.changes, request=request)
