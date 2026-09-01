from bot.services.ai_audit_tasks import finding_to_task
from bot.services.ai_repo_auditor import AuditFinding


def test_finding_to_task_contains_context_and_approval_gate():
    task = finding_to_task(AuditFinding("high", "bot/x.py", "Найден eval()", "dynamic execution"))
    assert "HIGH" in task.title
    assert "bot/x.py" in task.request
    assert "dynamic execution" in task.request
    assert "не меняй ничего до подтверждения администратора" in task.request
