from bot.services.ai_autopilot import AIAutopilot, ChangePlan
from bot.services.ai_autopilot_policy import is_cancel, is_confirmation
from bot.services.ai_executor import AuditedExecutor, ExecutionResult


def test_confirmation_and_cancel_are_explicit():
    assert is_confirmation("да")
    assert is_confirmation("ПОДТВЕРЖДАЮ")
    assert is_cancel("отмена")
    assert not is_confirmation("да, делай всё")


def test_executor_is_allowlist_only():
    executor = AuditedExecutor()
    assert executor.operations() == ()


def test_plan_has_confirmation_by_default():
    plan = ChangePlan(request="fix", summary="fix", risk="medium")
    assert plan.requires_confirmation is True
