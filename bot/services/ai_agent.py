from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

import config
from bot.ai_context import context_for
from bot.services.ai_key_store import AIKeyStore

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
    """XFI CONNECT AI adapter using the encrypted application key store."""

    _PROVIDER_ALIASES = {"openrouter": "groq", "deepseek": "groq"}

    def __init__(self, provider: str = "groq", key_store: AIKeyStore | None = None):
        self.provider = self._normalize_provider(provider)
        self.history: list[dict[str, str]] = []
        self.project_contract = _load_project_contract()
        self.key_store = key_store or AIKeyStore("data/ai_keys.enc")
        self._clients: dict[str, AsyncOpenAI] = {}
        self._refresh_client()

    @classmethod
    def _normalize_provider(cls, provider: str) -> str:
        return cls._PROVIDER_ALIASES.get((provider or "groq").strip().lower(), (provider or "groq").strip().lower())

    def _refresh_client(self) -> None:
        self._clients.clear()
        groq_key = self.key_store.get("groq")
        if groq_key:
            self._clients["groq"] = AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
        grok_key = self.key_store.get("grok")
        if grok_key:
            self._clients["grok"] = AsyncOpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")
        openai_key = self.key_store.get("openai")
        if openai_key:
            self._clients["openai"] = AsyncOpenAI(api_key=openai_key)

    def set_provider(self, provider: str) -> None:
        normalized = self._normalize_provider(provider)
        if normalized not in {"groq", "grok", "openai"}:
            raise ValueError(f"Неподдерживаемый AI-провайдер: {provider}")
        self.provider = normalized
        self._refresh_client()
        self.reset()

    def reset(self) -> None:
        self.history.clear()

    def _system_message(self, role: str, module_path: str | None = None) -> str:
        module_context = context_for(module_path or role)
        return ("Ты AI-инженер и ассистент администратора проекта XFI CONNECT.\n\n"
                "Работай как инженер: анализируй причину, учитывай архитектуру и зависимости, "
                "предлагай минимальное проверяемое изменение. Не выдумывай состояние системы, "
                "результаты команд, CI, коммиты или выполненные действия.\n\n"
                f"Текущий контекст: {role}\n\nКонтекст модуля:\n{module_context}\n\n"
                f"Общий контракт проекта:\n{self.project_contract}\n\n"
                "Приоритет: безопасность и сохранение рабочего состояния > корректность > минимальность > скорость. "
                "Для destructive/update/rollback действий сначала проверяй предусловия и требуй явного подтверждения.")

    async def _get_groq_model(self) -> str:
        configured = getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")
        client = self._clients.get("groq")
        if not client:
            return configured
        try:
            response = await client.models.list()
            model_ids = {item.id for item in getattr(response, "data", []) if getattr(item, "id", None)}
            if configured in model_ids:
                return configured
            for model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"):
                if model in model_ids:
                    return model
            return sorted(model_ids)[0] if model_ids else configured
        except Exception as exc:
            logger.warning("Не удалось получить список моделей Groq: %s", exc)
            return configured

    async def chat(self, prompt: str, *, role: str = "admin AI assistant", module_path: str | None = None) -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return "❌ Пустой запрос."
        self._refresh_client()
        if self.provider == "openai":
            return await self._call_openai(prompt, role=role, module_path=module_path)
        if self.provider == "grok":
            return await self._call_grok(prompt, role=role, module_path=module_path)
        return await self._call_groq(prompt, role=role, module_path=module_path)

    async def _call_openai(self, prompt: str, *, role: str, module_path: str | None) -> str:
        return await self._call_client("openai", prompt, getattr(config, "OPENAI_MODEL", "gpt-4.1-mini"), role=role, module_path=module_path)

    async def _call_groq(self, prompt: str, *, role: str, module_path: str | None) -> str:
        return await self._call_client("groq", prompt, await self._get_groq_model(), role=role, module_path=module_path)

    async def _call_grok(self, prompt: str, *, role: str, module_path: str | None) -> str:
        return await self._call_client("grok", prompt, getattr(config, "GROK_MODEL", "grok-3-mini"), role=role, module_path=module_path)

    async def _call_client(self, provider: str, prompt: str, model: str, *, role: str, module_path: str | None) -> str:
        client = self._clients.get(provider)
        if not client:
            return f"❌ API key для {provider} не настроен. Используйте /ai_keys."
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_message(role, module_path)}, *self.history[-20:], {"role": "user", "content": prompt}]
        try:
            response = await client.chat.completions.create(model=model, messages=messages, temperature=0.7)
            answer = response.choices[0].message.content or ""
            self._remember(prompt, answer)
            return answer or "❌ ИИ не вернул ответ."
        except Exception as exc:
            logger.exception("AI provider error: %s", provider)
            return f"❌ Ошибка AI-провайдера {provider}: {type(exc).__name__}"

    def _remember(self, prompt: str, answer: str) -> None:
        self.history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}])
        del self.history[:-20]
