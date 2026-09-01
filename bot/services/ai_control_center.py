"""Runtime composition root for the admin AI control plane.

This module only wires existing policy components together. It does not expose
shell access and it never bypasses ChangeSet approval.
"""
from __future__ import annotations

from pathlib import Path

from bot.services.ai_admin_pipeline import AIAdminPipeline
from bot.services.ai_admin_supervisor import AIAdminSupervisor
from bot.services.ai_agent import AIAgent
from bot.services.ai_changeset_approval import ChangeSetApprovalStore
from bot.services.ai_changeset_bridge import ChangeSetBridge
from bot.services.ai_model_selector import AIModelSelector
from bot.services.ai_proposal_service import AIProposalService
from bot.services.ai_task_router import AITaskRouter


class AIControlCenter:
    """Single runtime object shared by Telegram handlers."""

    def __init__(self, project_root: str | Path, inventory, key_store=None):
        root = Path(project_root).resolve()
        self.agent = AIAgent(key_store=key_store, inventory=inventory)
        self.selector = AIModelSelector(inventory)
        self.router = AITaskRouter(self.selector)
        self.supervisor = AIAdminSupervisor(self.router)
        self.bridge = ChangeSetBridge(root)
        self.approvals = ChangeSetApprovalStore()
        self.proposal_service = AIProposalService(self.agent, str(root))
        self.pipeline = AIAdminPipeline(self.proposal_service, AIAdminWorkflow(self.supervisor, self.bridge, self.approvals))

    def configure_telegram(self):
        from bot.services import ai_admin_telegram, ai_admin_workflow_telegram
        ai_admin_telegram.configure(self.supervisor, self.pipeline)
        ai_admin_workflow_telegram.configure(self.pipeline)
        return ai_admin_telegram.router, ai_admin_workflow_telegram.router
