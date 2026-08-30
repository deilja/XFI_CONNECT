"""Deterministic model selection using the monitored model inventory.

The selector never executes a model and never handles API secrets. It only
chooses from models already reported by the health/inventory layer.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    model: str
    reason: str


class AIModelSelector:
    _TASK_HINTS = {
        "code": ("code", "coder", "reason", "dev"),
        "analysis": ("reason", "thinking", "instruct", "analysis"),
        "fast": ("8b", "small", "mini", "flash", "instant", "fast"),
    }

    def __init__(self, inventory):
        self.inventory = inventory

    def choose(self, task: str, preferred_provider: str | None = None) -> ModelChoice | None:
        task = (task or "analysis").lower()
        available = self.inventory.available()
        if preferred_provider in available:
            providers = [preferred_provider] + [p for p in available if p != preferred_provider]
        else:
            providers = list(available)
        if not providers:
            return None

        def score(model: str) -> int:
            score = 0
            for hint in self._TASK_HINTS.get(task, self._TASK_HINTS["analysis"]):
                if hint in model.lower():
                    score += 10
            if any(x in model.lower() for x in ("70b", "72b", "120b", "405b")):
                score += 5
            return score

        for provider in providers:
            models = available[provider]
            selected = max(models, key=lambda m: (score(m), m))
            return ModelChoice(provider, selected, f"task={task}; inventory-available")
        return None
