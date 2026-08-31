import pytest

from bot.services.ai_admin_executor import GuardedAIExecutor


@pytest.mark.asyncio
async def test_executor_delegates_only_after_safe_policy():
    calls = []

    async def execute(text, plan):
        calls.append((text, plan))
        return "ok"

    async def verify(text, plan, result):
        return True

    async def rollback(task_id):
        return None

    executor = GuardedAIExecutor(execute, verify, rollback)
    assert await executor.execute("task", "plan") == "ok"
    assert calls == [("task", "plan")]


@pytest.mark.asyncio
async def test_executor_rejects_unsafe_policy():
    async def noop(*args):
        return None

    executor = GuardedAIExecutor(execute=noop, verify=lambda *a: None, rollback=noop)
    executor.policy = type("Policy", (), {"require_approval": False, "require_verification": True, "allow_rollback": True})()
    with pytest.raises(RuntimeError):
        await executor.execute("task", "plan")
