from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

import config
from bot.ai_context import context_for
from bot.services.ai_key_store import AIKeyStore
from bot.services.ai_model_selector import AIModelSelector

logger = logging.getLogger(__name__)

_PROJECT_CONTRACT_FALLBACK = """XFI CONNECT engineering contract:
- Repository: deilja/XFI_CONNECT; production branch: main.
- Preserve existing behaviour unless explicitly changing it.
- Never expose, hard-code or log secrets.
- Admin operations require existing authorization.
- Validate external input and fail closed on security-sensitive operations.
- Never claim an operation succeeded without verification.
"""


def _load_project_contract() -> str:
    root = Path(__file__).resolve().parents[2]
    parts: list[str] = []
    for path in (root / "AGENTS.md", root / ".github" / "copilot-instructions.md"):
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
        except OSError:
            continue
    return "\n\n".join(parts) if parts else _PROJECT_CONTRACT_FALLBACK


class AIAgent:
    """Unified AI adapter. Provider/model selection comes from monitored inventory."""

    def __init__(self, provider: str | None = None, key_store: AIKeyStore | None = None, inventory=None):
        self.provider = (provider or "").strip().lower() or None
        self.history: list[dict[str, str]] = []
        self.project_contract = _load_project_contract()
        self.key_store = key_store or AIKeyStore("data/ai_keys.enc")
        self.inventory = inventory
        self.selector = AIModelSelector(inventory) if inventory is not None else None
        self._clients: dict[str, AsyncOpenAI] = {}
        self._refresh_client()

    def _refresh_client(self) -> None:
        self._clients.clear()
        endpoints = {"groq": "https://api.groq.com/openai/v1", "grok": "https://api.x.ai/v1", "openai": None}
        for provider, base_url in endpoints.items():
            key = self.key_store.get(provider)
            if key:
                kwargs: dict[str, Any] = {"api_key": key}
                if base_url:
                    kwargs["base_url"] = base_url
                self._clients[provider] = AsyncOpenAI(**kwargs)

    def set_provider(self, provider: str) -> None:
        provider = provider.strip().lower()
        if provider not in {"groq", "grok", "openai"}:
            raise ValueError(f"Неподдерживаемый AI-провайдер: {provider}")
        self.provider = provider
        self.reset()

    def reset(self) -> None:
        self.history.clear()

    def _system_message(self, role: str, module_path: str | None = None) -> str:
        return ("Ты AI-инженер и ассистент администратора проекта XFI CONNECT.\n\n"
                "Анализируй причину и предлагай минимальное проверяемое изменение. "
                "Не выдумывай состояние системы, CI, коммиты или выполненные действия.\n\n"
                f"Текущий контекст: {role}\n\nКонтекст модуля:\n{context_for(module_path or role)}\n\n"
                f"Общий контракт проекта:\n{self.project_contract}")

    def _choice(self, task_type: str) -> tuple[str, str] | None:
        if self.selector is not None:
            choice = self.selector.choose(task_type, preferred_provider=self.provider)
            if choice:
                return choice.provider, choice.model
            return None
        if self.provider and self.provider in self._clients:
            defaults = {"groq": getattr(config, "GROQ_MODEL", ""), "grok": getattr(config, "GROK_MODEL", ""), "openai": getattr(config, "OPENAI_MODEL", "")}
            return self.provider, defaults[self.provider]
        return None

    async def chat(self, prompt: str, *, role: str = "admin AI assistant", module_path: str | None = None, task_type: str = "analysis") -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return "❌ Пустой запрос."
        self._refresh_client()
        choice = self._choice(task_type)
        if not choice:
            return "❌ Нет доступного AI-провайдера или модели. Настройте рабочий ключ через /ai_keys."
        provider, model = choice
        client = self._clients.get(provider)
        if not client or not model:
            return "❌ Выбранный AI-провайдер недоступен."
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_message(role, module_path)}, *self.history[-20:], {"role": "user", "content": prompt}]
        try:
            response = await client.chat.completions.create(model=model, messages=messages, temperature=0.7)
            answer = response.choices[0].message.content or ""
            self._remember(prompt, answer)
            return answer or "❌ ИИ не вернул ответ."
        except Exception as exc:
            logger.warning("AI request failed provider=%s error=%s", provider, type(exc).__name__)
            return f"❌ Ошибка AI-провайдера {provider}: {type(exc).__name__}"

    def _remember(self, prompt: str, answer: str) -> None:
        self.history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}])
        del self.history[:-20]
