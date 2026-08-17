from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

import config

logger = logging.getLogger(__name__)


class AIAgent:
    """Small provider adapter for the admin AI chat.

    The project currently uses Groq and xAI's OpenAI-compatible APIs.  Older
    values (``openrouter``/``deepseek``) are kept as aliases for Groq so an
    existing config does not break after an update.
    """

    _PROVIDER_ALIASES = {
        "openrouter": "groq",
        "deepseek": "groq",
    }

    def __init__(self, provider: str = "groq"):
        self.provider = self._normalize_provider(provider)
        self.history: list[dict[str, str]] = []

        groq_key = getattr(config, "GROQ_API_KEY", "") or ""
        self.groq_client = (
            AsyncOpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
            )
            if groq_key
            else None
        )

        grok_key = getattr(
            config,
            "GROK_API_KEY",
            getattr(config, "XAI_API_KEY", ""),
        ) or ""
        self.grok_client = (
            AsyncOpenAI(
                api_key=grok_key,
                base_url="https://api.x.ai/v1",
            )
            if grok_key
            else None
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

    def reset(self) -> None:
        self.history.clear()

    async def _get_groq_model(self) -> str:
        """Return a configured/available Groq chat model.

        Groq does not expose OpenRouter's ``:free`` model suffix, so the old
        catalogue filter was incorrect and caused unnecessary fallback calls.
        """
        configured = getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")
        if not self.groq_client:
            return configured

        try:
            response = await self.groq_client.models.list()
            model_ids = {
                item.id
                for item in getattr(response, "data", [])
                if getattr(item, "id", None)
            }
            if configured in model_ids:
                return configured

            preferred = (
                "llama-3.3-70b-versatile",
                "llama-3.1-8b-instant",
                "openai/gpt-oss-120b",
            )
            for model in preferred:
                if model in model_ids:
                    return model

            # Pick a model advertised by the API rather than sending requests
            # to a hard-coded, possibly retired model.
            if model_ids:
                return sorted(model_ids)[0]
        except Exception as exc:
            logger.warning("Не удалось получить список моделей Groq: %s", exc)

        return configured

    async def chat(self, prompt: str) -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return "❌ Пустой запрос."

        if self.provider == "grok":
            return await self._call_grok(prompt)
        return await self._call_groq(prompt)

    async def _call_groq(self, prompt: str) -> str:
        if not self.groq_client:
            return "❌ Ошибка: GROQ_API_KEY не указан в config.py"

        model_name = await self._get_groq_model()
        system_message = (
            "Ты полезный и умный ИИ-ассистент администратора VPN-сервиса. "
            "Отвечай по-русски кратко и по делу."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_message},
            *self.history[-20:],
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.groq_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.7,
            )
            answer = response.choices[0].message.content or ""
            self._remember(prompt, answer)
            return answer or "❌ ИИ не вернул ответ."
        except Exception as exc:
            logger.exception("Groq error")
            return f"❌ Ошибка Groq: {exc}"

    async def _call_grok(self, prompt: str) -> str:
        if not self.grok_client:
            return "❌ Ошибка: GROK_API_KEY не указан в config.py"

        model_name = getattr(config, "GROK_MODEL", "grok-3-mini")
        system_message = (
            "Ты полезный и умный ИИ-ассистент администратора VPN-сервиса. "
            "Отвечай по-русски кратко и по делу."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_message},
            *self.history[-20:],
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.grok_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.7,
            )
            answer = response.choices[0].message.content or ""
            self._remember(prompt, answer)
            return answer or "❌ ИИ не вернул ответ."
        except Exception as exc:
            logger.exception("Grok error")
            return f"❌ Ошибка Grok: {exc}"

    def _remember(self, prompt: str, answer: str) -> None:
        self.history.extend(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ]
        )
        del self.history[:-20]
