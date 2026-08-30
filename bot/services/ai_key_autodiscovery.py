"""Detect an unknown AI API key by harmless provider-specific probes.

The key is never logged, returned, or persisted until a provider responds
successfully. Only providers explicitly registered here are probed.
"""
from __future__ import annotations

from dataclasses import dataclass
import asyncio
import re
from typing import Awaitable, Callable

import httpx


@dataclass(frozen=True)
class ProviderProbe:
    provider: str
    endpoint: str
    prefix: str


PROBES = (
    ProviderProbe("groq", "https://api.groq.com/openai/v1/models", "gsk_"),
    ProviderProbe("grok", "https://api.x.ai/v1/models", "xai-"),
    ProviderProbe("openai", "https://api.openai.com/v1/models", "sk-"),
)


def _looks_like_key(value: str) -> bool:
    return 20 <= len(value) <= 4096 and not any(c.isspace() for c in value)


async def probe_api_key(probe: ProviderProbe, api_key: str, timeout: float = 8.0) -> bool:
    if not _looks_like_key(api_key):
        return False
    if probe.prefix and not api_key.startswith(probe.prefix):
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(
                probe.endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            )
        return response.status_code == 200
    except (httpx.HTTPError, TimeoutError):
        return False


async def autodetect_provider(api_key: str, timeout: float = 8.0) -> str | None:
    """Return the provider only after an authenticated 200 response."""
    if not _looks_like_key(api_key):
        return None
    candidates = [p for p in PROBES if not p.prefix or api_key.startswith(p.prefix)]
    if not candidates:
        candidates = list(PROBES)
    results = await asyncio.gather(*(probe_api_key(p, api_key, timeout) for p in candidates), return_exceptions=True)
    matches = [probe.provider for probe, result in zip(candidates, results) if result is True]
    return matches[0] if len(matches) == 1 else None
