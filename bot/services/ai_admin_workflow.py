"""End-to-end orchestration: proposal -> immutable approval -> apply -> verify.

The workflow is deliberately executor-agnostic. A real ChangeSet executor must
be injected by the application; no shell command is accepted from AI text.
"""
from __future__ import annotations

from dataclasses import dataclass

from bot.services.ai_admin_supervisor import AIAdminSupervisor, AdminTask, TaskStage
from bot.services.ai_changeset import ChangeSet
from bot.services.ai_changeset_approval import ApprovalRecord, ChangeSetApprovalStore
from bot.services.ai_changeset_bridge import ChangeSetBridge, ProposedChange


@dataclass(frozen=True)
class PendingChange:
    task_id: str
    changeset: ChangeSet
    approval: ApprovalRecord
    preview: str


class AIAdminWorkflow:
    def __init__(self, supervisor: AIAdminSupervisor, bridge: ChangeSetBridge, approvals: ChangeSetApprovalStore | None = None):
        self.supervisor = supervisor
        self.bridge = bridge
        self.approvals = approvals or ChangeSetApprovalStore()
        self.pending: dict[str, PendingChange] = {}
        self.transactions = {}

    def prepare(self, task_id: str, proposed: list[ProposedChange], request: str | None = None) -> PendingChange:
        task = self.supervisor._get(task_id)
        changeset = self.bridge.build(request or task.text, proposed)
        self.supervisor.set_plan(task_id, self.bridge.preview(changeset))
        approval = self.approvals.issue(task_id, changeset)
        pending = PendingChange(task_id, changeset, approval, self.bridge.preview(changeset))
        self.pending[task_id] = pending
        return pending

    def approve(self, task_id: str, token: str) -> AdminTask:
        pending = self._pending(task_id)
        self.approvals.approve(task_id, token, pending.changeset)
        return self.supervisor.approve(task_id, token=self.supervisor._get(task_id).approval_token or "")

    def begin_transaction(self, task_id: str):
        pending = self._pending(task_id)
        if not self.approvals.is_approved(task_id, pending.changeset):
            raise PermissionError("ChangeSet не подтверждён")
        task = self.supervisor._get(task_id)
        if task.stage != TaskStage.EXECUTE:
            raise ValueError("Задача не находится на этапе EXECUTE")
        tx = self.bridge.start(pending.changeset)
        self.transactions[task_id] = tx
        return tx

    def apply(self, task_id: str) -> None:
        pending = self._pending(task_id)
        tx = self.transactions.get(task_id)
        if tx is None:
            raise ValueError("Transaction не создан")
        self.bridge.apply(tx, pending.changeset)

    async def verify_and_finish(self, task_id: str) -> AdminTask:
        pending = self._pending(task_id)
        tx = self.transactions.get(task_id)
        if tx is None:
            raise ValueError("Transaction не создан")
        task = await self.supervisor.execute(task_id)
        if task.stage == TaskStage.VERIFY:
            task = await self.supervisor.verify(task_id)
        if task.stage == TaskStage.ROLLBACK:
            self.bridge.verify_and_commit(tx, pending.changeset, False)
            task = await self.supervisor.rollback(task_id)
        elif task.stage == TaskStage.DONE:
            self.bridge.verify_and_commit(tx, pending.changeset, True)
        return task

    def _pending(self, task_id: str) -> PendingChange:
        try:
            return self.pending[task_id]
        except KeyError as exc:
            raise ValueError("ChangeSet не подготовлен") from exc
