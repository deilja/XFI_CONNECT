"""Fail-closed AI provider pool with health, cooldown and model discovery."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from bot.services.ai_key_store import AIKeyStore


@dataclass
class ProviderState:
    provider: str
    failures: int = 0
    successes: int = 0
    cooldown_until: float = 0.0
    last_error: str | None = None
    models: tuple[str, ...] = field(default_factory=tuple)


class AIProviderPool:
    PROVIDERS = ("groq", "grok", "openai")
    BASE_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "grok": "https://api.x.ai/v1",
        "openai": None,
    }

    def __init__(self, store: AIKeyStore, cooldown_seconds: int = 60):
        self.store = store
        self.cooldown_seconds = max(1, cooldown_seconds)
        self.states = {name: ProviderState(name) for name in self.PROVIDERS}

    def configured(self) -> tuple[str, ...]:
        return tuple(name for name in self.PROVIDERS if self.store.configured(name))

    def healthy(self) -> tuple[str, ...]:
        now = time.monotonic()
        return tuple(name for name in self.configured() if self.states[name].cooldown_until <= now)

    def status(self) -> tuple[dict[str, Any], ...]:
        now = time.monotonic()
        return tuple({
            "provider": s.provider,
            "configured": self.store.configured(s.provider),
            "healthy": self.store.configured(s.provider) and s.cooldown_until <= now,
            "failures": s.failures,
            "successes": s.successes,
            "cooldown": max(0, int(s.cooldown_until - now)),
            "models": s.models,
            "last_error": s.last_error,
        } for s in self.states.values())

    def _client(self, provider: str) -> AsyncOpenAI:
        key = self.store.get(provider)
        if not key:
            raise RuntimeError(f"API key for {provider} is not configured")
        return AsyncOpenAI(api_key=key, base_url=self.BASE_URLS[provider])

    async def refresh_models(self, provider: str) -> tuple[str, ...]:
        client = self._client(provider)
        try:
            response = await client.models.list()
            models = tuple(sorted({m.id for m in getattr(response, "data", []) if getattr(m, "id", None)}))
            state = self.states[provider]
            state.models = models
            state.failures = 0
            state.last_error = None
            state.cooldown_until = 0
            state.successes += 1
            return models
        except Exception as exc:
            self._failure(provider, exc)
            raise
        finally:
            await client.close()

    def _failure(self, provider: str, exc: Exception) -> None:
        state = self.states[provider]
        state.failures += 1
        state.last_error = type(exc).__name__
        state.cooldown_until = time.monotonic() + self.cooldown_seconds

    def _success(self, provider: str) -> None:
        state = self.states[provider]
        state.successes += 1
        state.failures = 0
        state.last_error = None
        state.cooldown_until = 0

    async def chat(self, messages: list[dict[str, str]], models: dict[str, str], preferred: str | None = None) -> tuple[str, str]:
        order = [preferred] if preferred in self.PROVIDERS else []
        order.extend(name for name in self.PROVIDERS if name not in order)
        last_error: Exception | None = None
        for provider in order:
            if not self.store.configured(provider) or self.states[provider].cooldown_until > time.monotonic():
                continue
            model = models.get(provider)
            if not model:
                continue
            client = self._client(provider)
            try:
                response = await client.chat.completions.create(model=model, messages=messages, temperature=0.7)
                answer = response.choices[0].message.content or ""
                self._success(provider)
                return provider, answer
            except Exception as exc:
                last_error = exc
                self._failure(provider, exc)
            finally:
                await client.close()
        raise RuntimeError(f"All configured AI providers failed: {type(last_error).__name__ if last_error else 'none'}")
