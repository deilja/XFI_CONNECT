"""Route plain-language admin requests to a safe AI model choice."""
from __future__ import annotations

from dataclasses import dataclass

from bot.services.ai_model_selector import AIModelSelector, ModelChoice


@dataclass(frozen=True)
class RoutedTask:
    text: str
    task_type: str
    choice: ModelChoice | None


class AITaskRouter:
    """Classifies an admin request conservatively and selects a model.

    This component only plans/routs. It cannot edit files, execute commands,
    deploy changes, or access API secrets.
    """

    def __init__(self, selector: AIModelSelector):
        self.selector = selector

    @staticmethod
    def classify(text: str) -> str:
        value = (text or "").lower()
        if any(x in value for x in ("код", "python", "bug", "ошибк", "исправ", "файл", "репозитор")):
            return "code"
        if any(x in value for x in ("быстро", "коротко", "статус", "проверь доступность")):
            return "fast"
        return "analysis"

    def route(self, text: str, preferred_provider: str | None = None) -> RoutedTask:
        task_type = self.classify(text)
        choice = self.selector.choose(task_type, preferred_provider=preferred_provider)
        return RoutedTask(text=(text or "").strip(), task_type=task_type, choice=choice)
