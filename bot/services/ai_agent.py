from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

import config

logger = logging.getLogger(__name__)

_PROJECT_CONTRACT_FALLBACK = """XFI CONNECT engineering contract:
- Repository: deilja/XFI_CONNECT; production branch: main.
- Preserve existing behaviour unless explicitly changing it.
- Never reintroduce YadrenoVPN updater behaviour.
- Never expose, hard-code or log secrets.
- Admin operations require existing authorization.
- Validate external input and fail closed on security-sensitive operations.
- Update/rollback must remain transactional, locked and recoverable.
- Canonical updater: bot/services/xfi_update.py.
- Compatibility updater: bot/services/update_rollback.py.
- Do not mutate Git remotes dynamically.
- Never claim an operation succeeded without verification.
- For code tasks inspect callers/tests, make minimal changes and add regression tests.
"""


def _load_project_contract() -> str:
    """Load the repository-wide AI contract for every assistant conversation."""
    candidates = (
        Path(__file__).resolve().parents[2] / "AGENTS.md",
        Path(__file__).resolve().parents[2] / ".github" / "copilot-instructions.md",
    )
    parts: list[str] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
        except OSError:
            continue
    return "\n\n".join(parts) if parts else _PROJECT_CONTRACT_FALLBACK


class AIAgent:
    """Provider adapter with the XFI CONNECT engineering policy injected into every request."""

    _PROVIDER_ALIASES = {
        "openrouter": "groq",
        "deepseek": "groq",
    }

    def __init__(self, provider: str = "groq"):
        self.provider = self._normalize_provider(provider)
        self.history: list[dict[str, str]] = []
        self.project_contract = _load_project_contract()

        groq_key = getattr(config, "GROQ_API_KEY", "") or ""
        self.groq_client = (
            AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            if groq_key else None
        )

        grok_key = getattr(config, "GROK_API_KEY", getattr(config, "XAI_API_KEY", "")) or ""
        self.grok_client = (
            AsyncOpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")
            if grok_key else None
        )

    @classmethod
    def _normalize_provider(cls, provider: str) -> str:
        value = (provider or "groq").strip().lower()
        return cls._PROVIDER_ALIASES.get(value, value)

    def set_provider(self, provider: str) -> None:
        normalized = self._normalize_provider(provider)
        if normalized not in {"groq", "grok"}:
            raise ValueError(f"Неподдерживаемый AI-провайдер: {provider}")
        self.provider = normalized
        self.reset()

    def _system_message(self, role: str) -> str:
        return (
            "Ты AI-инженер и ассистент администратора проекта XFI CONNECT.\n\n"
            "Твоя задача — помогать безопасно поддерживать и развивать этот проект. "
            "Не выдумывай состояние системы, результаты команд, коммиты, CI или выполненные действия. "
            "Если данных недостаточно — прямо укажи, что нужно проверить.\n\n"
            f"Текущий модуль/контекст: {role}\n\n"
            "Обязательный инженерный контракт проекта:\n"
            f"{self.project_contract}\n\n"
            "Приоритет: безопасность и сохранение рабочего состояния > минимальное изменение > скорость. "
            "Для destructive/update/rollback действий сначала проверяй предусловия и существующий workflow."
        )

    async def _get_groq_model(self) -> str:
        configured = getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")
        if not self.groq_client:
            return configured
        try:
            response = await self.groq_client.models.list()
            model_ids = {item.id for item in getattr(response, "data", []) if getattr(item, "id", None)}
            if configured in model_ids:
                return configured
            for model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"):
                if model in model_ids:
                    return model
            if model_ids:
                return sorted(model_ids)[0]
        except Exception as exc:
            logger.warning("Не удалось получить список моделей Groq: %s", exc)
        return configured

    async def chat(self, prompt: str, *, role: str = "admin AI assistant") -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return "❌ Пустой запрос."
        if self.provider == "grok":
            return await self._call_grok(prompt, role=role)
        return await self._call_groq(prompt, role=role)

    async def _call_groq(self, prompt: str, *, role: str) -> str:
        if not self.groq_client:
            return "❌ Ошибка: GROQ_API_KEY не указан в config.py"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_message(role)},
            *self.history[-20:],
            {"role": "user", "content": prompt},
        ]
        try:
            response = await self.groq_client.chat.completions.create(
                model=await self._get_groq_model(), messages=messages, temperature=0.7,
            )
            answer = response.choices[0].message.content or ""
            self._remember(prompt, answer)
            return answer or "❌ ИИ не вернул ответ."
        except Exception as exc:
            logger.exception("Groq error")
            return f"❌ Ошибка Groq: {exc}"

    async def _call_grok(self, prompt: str, *, role: str) -> str:
        if not self.grok_client:
            return "❌ Ошибка: GROK_API_KEY не указан в config.py"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_message(role)},
            *self.history[-20:],
            {"role": "user", "content": prompt},
        ]
        try:
            response = await self.grok_client.chat.completions.create(
                model=getattr(config, "GROK_MODEL", "grok-3-mini"),
                messages=messages, temperature=0.7,
            )
            answer = response.choices[0].message.content or ""
            self._remember(prompt, answer)
            return answer or "❌ ИИ не вернул ответ."
        except Exception as exc:
            logger.exception("Grok error")
            return f"❌ Ошибка Grok: {exc}"

    def _remember(self, prompt: str, answer: str) -> None:
        self.history.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ])
        del self.history[:-20]
