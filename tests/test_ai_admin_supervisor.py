import pytest

from bot.services.ai_admin_supervisor import AIAdminSupervisor, TaskStage


class Router:
    def route(self, text):
        return type("Route", (), {"text": text, "task_type": "code"})()


class Executor:
    async def execute(self, text, plan):
        return "changed"

    async def verify(self, text, plan, result):
        return True


@pytest.mark.asyncio
async def test_execution_requires_approval():
    supervisor = AIAdminSupervisor(Router(), Executor())
    task = supervisor.create_task("исправь баг")
    supervisor.set_plan(task.task_id, "исправить только test.py")
    assert task.stage == TaskStage.WAIT_APPROVAL
    with pytest.raises(ValueError):
        await supervisor.execute(task.task_id)
    supervisor.approve(task.task_id, task.approval_token)
    await supervisor.execute(task.task_id)
    await supervisor.verify(task.task_id)
    assert task.stage == TaskStage.DONE
