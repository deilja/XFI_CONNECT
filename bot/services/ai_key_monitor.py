"""Periodic health monitor for encrypted AI provider keys.

A failed check disables a provider from selection temporarily; its encrypted
key remains stored. No key material is returned, logged, or written to audit.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from bot.services.ai_key_store import AIKeyStore

Check = Callable[[str], Awaitable[bool]]


@dataclass
class ProviderHealth:
    provider: str
    configured: bool = False
    healthy: bool = False
    failures: int = 0
    last_error: str | None = None
    last_checked: float | None = None
    disabled_until: float = 0.0

    @property
    def enabled(self) -> bool:
        return self.configured and self.healthy and time.time() >= self.disabled_until


class AIKeyHealthMonitor:
    def __init__(self, store: AIKeyStore, providers: tuple[str, ...], check: Check, cooldown: int = 900):
        self.store = store
        self.providers = providers
        self.check = check
        self.cooldown = cooldown
        self.state = {p: ProviderHealth(p) for p in providers}
        self._lock = asyncio.Lock()

    async def check_provider(self, provider: str) -> ProviderHealth:
        async with self._lock:
            status = self.state[provider]
            key = self.store.get(provider)
            status.configured = bool(key)
            status.last_checked = time.time()
            if not key:
                status.healthy = False
                status.last_error = "not_configured"
                return status
            try:
                ok = bool(await self.check(provider))
                status.healthy = ok
                if ok:
                    status.failures = 0
                    status.last_error = None
                    status.disabled_until = 0.0
                else:
                    status.failures += 1
                    status.last_error = "provider_check_failed"
                    status.disabled_until = time.time() + self.cooldown
            except Exception as exc:
                status.healthy = False
                status.failures += 1
                status.last_error = type(exc).__name__
                status.disabled_until = time.time() + self.cooldown
            return status

    async def check_all(self) -> dict[str, ProviderHealth]:
        results = {}
        for provider in self.providers:
            results[provider] = await self.check_provider(provider)
        return results

    def available(self) -> tuple[str, ...]:
        return tuple(p for p, state in self.state.items() if state.enabled)
