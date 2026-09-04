from __future__ import annotations

import logging
import os
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
    """Unified AI adapter with monitored model selection and bounded failover."""

    MAX_ATTEMPTS = 3

    def __init__(self, provider: str | None = None, key_store: AIKeyStore | None = None, inventory=None):
        self.provider = self._normalize_provider(provider) if provider else None
        self.history: list[dict[str, str]] = []
        self.project_contract = _load_project_contract()
        self.key_store = key_store
        self.inventory = inventory
        self.selector = AIModelSelector(inventory) if inventory is not None else None
        self._clients: dict[str, AsyncOpenAI] = {}
        self._keystore_error: str | None = None
        if self.key_store is None:
            master_key = os.getenv("XFI_AI_KEYSTORE_MASTER_KEY", "")
            if len(master_key) >= 32:
                self.key_store = AIKeyStore("data/ai_keys.enc", master_key=master_key)
            else:
                self._keystore_error = "XFI_AI_KEYSTORE_MASTER_KEY is not configured"
        self._refresh_client()

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        aliases = {
            "deepseek": "groq",
            "openrouter": "groq",
        }
        normalized = provider.strip().lower()
        return aliases.get(normalized, normalized)

    def _refresh_client(self) -> None:
        self._clients.clear()
        if self.key_store is None:
            return
        endpoints = {"groq": "https://api.groq.com/openai/v1", "grok": "https://api.x.ai/v1", "openai": None}
        for provider, base_url in endpoints.items():
            key = self.key_store.get(provider)
            if key:
                kwargs: dict[str, Any] = {"api_key": key}
                if base_url:
                    kwargs["base_url"] = base_url
                self._clients[provider] = AsyncOpenAI(**kwargs)

    def set_provider(self, provider: str) -> None:
        provider = self._normalize_provider(provider)
        if provider not in {"groq", "grok", "openai"}:
            raise ValueError(f"Неподдерживаемый AI-провайдер: {provider}")
        self.provider = provider
        self.reset()

    def reset(self) -> None:
        self.history.clear()

    def _system_message(self, role: str, module_path: str | None = None) -> str:
        return (
            "Ты AI-инженер и ассистент администратора проекта XFI CONNECT.\n\n"
            "Анализируй причину и предлагай минимальное проверяемое изменение. "
            "Не выдумывай состояние системы, CI, коммиты или выполненные действия.\n\n"
            f"Текущий контекст: {role}\n\nКонтекст модуля:\n{context_for(module_path or role)}\n\n"
            f"Общий контракт проекта:\n{self.project_contract}"
        )

    def _candidate_choices(self, task_type: str) -> list[tuple[str, str]]:
        if self.selector is None:
            if self.provider and self.provider in self._clients:
                defaults = {
                    "groq": getattr(config, "GROQ_MODEL", ""),
                    "grok": getattr(config, "GROK_MODEL", ""),
                    "openai": getattr(config, "OPENAI_MODEL", ""),
                }
                return [(self.provider, defaults[self.provider])]
            return []
        available = self.inventory.available()
        providers = list(available)
        if self.provider in available:
            providers.remove(self.provider)
            providers.insert(0, self.provider)
        choices: list[tuple[str, str]] = []
        for provider in providers:
            selected = self.selector.choose(task_type, preferred_provider=provider)
            if selected:
                choices.append((selected.provider, selected.model))
        return choices

    async def chat(
        self,
        prompt: str,
        *,
        role: str = "admin AI assistant",
        module_path: str | None = None,
        task_type: str = "analysis",
    ) -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return "❌ Пустой запрос."
        self._refresh_client()
        choices = self._candidate_choices(task_type)[: self.MAX_ATTEMPTS]
        if not choices:
            return "❌ Нет доступного AI-провайдера или модели. Настройте рабочий ключ через /ai_keys."
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_message(role, module_path)},
            *self.history[-20:],
            {"role": "user", "content": prompt},
        ]
        failures: list[str] = []
        for provider, model in choices:
            client = self._clients.get(provider)
            if not client or not model:
                failures.append(f"{provider}:unavailable")
                continue
            try:
                response = await client.chat.completions.create(model=model, messages=messages, temperature=0.7)
                answer = response.choices[0].message.content or ""
                if answer:
                    self._remember(prompt, answer)
                    return answer
                failures.append(f"{provider}:empty_response")
            except Exception as exc:
                logger.warning("AI request failed provider=%s error=%s", provider, type(exc).__name__)
                failures.append(f"{provider}:{type(exc).__name__}")
                continue
        logger.warning("All AI candidates failed: %s", ",".join(failures))
        return "❌ Все доступные AI-провайдеры не смогли обработать запрос."

    def _remember(self, prompt: str, answer: str) -> None:
        self.history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}])
        del self.history[:-20]
