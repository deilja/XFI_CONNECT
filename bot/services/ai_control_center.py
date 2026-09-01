"""Runtime composition root for the admin AI control plane."""
from __future__ import annotations

from pathlib import Path

from bot.services.ai_admin_pipeline import AIAdminPipeline
from bot.services.ai_admin_supervisor import AIAdminSupervisor
from bot.services.ai_admin_workflow import AIAdminWorkflow
from bot.services.ai_agent import AIAgent
from bot.services.ai_changeset_approval import ChangeSetApprovalStore
from bot.services.ai_changeset_bridge import ChangeSetBridge
from bot.services.ai_model_selector import AIModelSelector
from bot.services.ai_proposal_service import AIProposalService
from bot.services.ai_task_router import AITaskRouter
from bot.services.ai_repo_auditor import RepositoryAuditor
from bot.services.ai_audit_loop import AIAuditLoop
from bot.services.ai_audit_telegram import AIAuditTelegramReporter


class AIControlCenter:
    """Single runtime object shared by Telegram handlers and audit services."""

    def __init__(self, project_root: str | Path, inventory, key_store=None, bot=None, admin_ids=None):
        root = Path(project_root).resolve()
        self.agent = AIAgent(key_store=key_store, inventory=inventory)
        self.selector = AIModelSelector(inventory)
        self.router = AITaskRouter(self.selector)
        self.supervisor = AIAdminSupervisor(self.router)
        self.bridge = ChangeSetBridge(root)
        self.approvals = ChangeSetApprovalStore()
        self.proposal_service = AIProposalService(self.agent, str(root))
        self.workflow = AIAdminWorkflow(self.supervisor, self.bridge, self.approvals)
        self.pipeline = AIAdminPipeline(self.proposal_service, self.workflow)
        self.audit_reporter = None
        self.audit_loop = None
        if bot is not None and admin_ids:
            self.audit_reporter = AIAuditTelegramReporter(bot, admin_ids)
            self.audit_reporter.configure(self.supervisor, self.pipeline)
            self.audit_loop = AIAuditLoop(RepositoryAuditor(root), self.audit_reporter, interval=3600)

    def configure_telegram(self):
        from bot.services import ai_admin_telegram, ai_admin_workflow_telegram, ai_audit_telegram
        ai_admin_telegram.configure(self.supervisor, self.pipeline)
        ai_admin_workflow_telegram.configure(self.pipeline)
        return ai_admin_telegram.router, ai_admin_workflow_telegram.router, ai_audit_telegram.router

    def start_audit(self):
        if self.audit_loop is not None:
            self.audit_loop.start()

    async def stop(self):
        if self.audit_loop is not None:
            await self.audit_loop.stop()
