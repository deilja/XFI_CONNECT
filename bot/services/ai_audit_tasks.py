"""Turn a concrete audit finding into a normal AI task request."""
from __future__ import annotations

from dataclasses import dataclass

from bot.services.ai_repo_auditor import AuditFinding


@dataclass(frozen=True)
class AuditTaskRequest:
    title: str
    request: str


def finding_to_task(finding: AuditFinding) -> AuditTaskRequest:
    title = f"[{finding.severity.upper()}] {finding.title} — {finding.path}"
    request = (
        "Исправь обнаруженную проблему безопасно. "
        "Сначала проанализируй файл и связанные участки кода, "
        "не меняй ничего до подтверждения администратора. "
        f"Файл: {finding.path}. Проблема: {finding.title}. "
        f"Детали: {finding.detail}. "
        "Предложи минимальный ChangeSet и объясни риск."
    )
    return AuditTaskRequest(title, request)
