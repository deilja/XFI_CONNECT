"""Automatic provider detection for administrator-supplied AI API keys.

Detection is conservative: a prefix is only a hint. A candidate is confirmed
only after a provider-specific authenticated API request succeeds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

from bot.services.ai_key_manager import AIKeyManager


@dataclass(frozen=True)
class DetectionResult:
    provider: str | None
    valid: bool
    models: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class ProviderProbe:
    provider: str
    base_url: str
    prefixes: tuple[str, ...]


PROBES = (
    ProviderProbe("groq", "https://api.groq.com/openai/v1", ("gsk_",)),
    ProviderProbe("grok", "https://api.x.ai/v1", ("xai-",)),
    ProviderProbe("openai", "https://api.openai.com/v1", ("sk-", "sk-proj-")),
)


class AIKeyAutoDetector:
    def __init__(self, manager: AIKeyManager, timeout: float = 10.0):
        self.manager = manager
        self.timeout = timeout

    @staticmethod
    def _candidates(key: str) -> tuple[ProviderProbe, ...]:
        normalized = key.strip()
        hinted = [p for p in PROBES if any(normalized.startswith(prefix) for prefix in p.prefixes)]
        return tuple(hinted or PROBES)

    async def detect(self, api_key: str) -> DetectionResult:
        key = api_key.strip()
        if not key or len(key) > 4096:
            return DetectionResult(None, False, reason="invalid_key_format")
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            for probe in self._candidates(key):
                try:
                    response = await client.get(
                        f"{probe.base_url}/models",
                        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                    )
                except httpx.HTTPError:
                    continue
                if response.status_code != 200:
                    continue
                try:
                    payload = response.json()
                    models = tuple(
                        str(item.get("id")) for item in payload.get("data", [])
                        if isinstance(item, dict) and item.get("id")
                    )
                except (ValueError, AttributeError):
                    models = ()
                if not models:
                    continue
                # Confirmed only by the authenticated provider endpoint.
                await self.manager.validate_and_set(probe.provider, key)
                return DetectionResult(probe.provider, True, models=models, reason="authenticated_models_probe")
        return DetectionResult(None, False, reason="no_provider_authenticated")
