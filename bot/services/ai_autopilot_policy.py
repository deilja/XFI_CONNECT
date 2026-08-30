"""Policy helpers for the unified AI autopilot."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPolicy:
    require_confirmation: bool = True
    allow_code_changes: bool = True
    allow_service_restart: bool = False
    allow_git_push: bool = False
    allow_destructive: bool = False


DEFAULT_POLICY = ExecutionPolicy()


SAFE_CONFIRMATIONS = {
    "да", "подтверждаю", "подтвердить", "выполняй", "выполнить", "применяй", "применить"
}
CANCEL_WORDS = {"нет", "отмена", "отменить", "cancel", "стоп"}


def is_confirmation(text: str) -> bool:
    return text.strip().lower() in SAFE_CONFIRMATIONS


def is_cancel(text: str) -> bool:
    return text.strip().lower() in CANCEL_WORDS
