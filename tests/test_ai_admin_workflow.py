from pathlib import Path

import pytest

from bot.services.ai_admin_supervisor import AIAdminSupervisor
from bot.services.ai_changeset import ChangeSetError
from bot.services.ai_changeset_bridge import ChangeSetBridge, ProposedChange
from bot.services.ai_changeset_approval import ChangeSetApprovalStore
from bot.services.ai_admin_workflow import AIAdminWorkflow


class Router:
    def route(self, text):
        return type("Routed", (), {"text": text, "task_type": "code"})()


class Executor:
    async def execute(self, text, plan):
        return "executed"

    async def verify(self, text, plan, result):
        return True

    async def rollback(self, task_id):
        pass


def test_prepare_and_approve(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("old\n", encoding="utf-8")
    supervisor = AIAdminSupervisor(Router(), Executor())
    workflow = AIAdminWorkflow(supervisor, ChangeSetBridge(tmp_path), ChangeSetApprovalStore())
    task = supervisor.create_task("fix app")
    pending = workflow.prepare(task.task_id, [ProposedChange("app.py", "new\n")])
    approved = workflow.approve(task.task_id, pending.approval.token)
    assert approved.stage.value == "execute"


@pytest.mark.asyncio
async def test_execute_verify_commit(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("old\n", encoding="utf-8")
    supervisor = AIAdminSupervisor(Router(), Executor())
    workflow = AIAdminWorkflow(supervisor, ChangeSetBridge(tmp_path))
    task = supervisor.create_task("fix app")
    pending = workflow.prepare(task.task_id, [ProposedChange("app.py", "new\n")])
    workflow.approve(task.task_id, pending.approval.token)
    workflow.begin_transaction(task.task_id)
    workflow.apply(task.task_id)
    result = await workflow.verify_and_finish(task.task_id)
    assert result.stage.value == "done"
    assert target.read_text(encoding="utf-8") == "new\n"
