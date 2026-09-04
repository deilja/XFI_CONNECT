"""Background scheduler for AI provider key health checks.

The loop is application-owned: the AI model cannot change its interval,
providers, notification policy, or callback.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from bot.services.ai_key_monitor import AIKeyHealthMonitor, ProviderHealth

logger = logging.getLogger(__name__)

Notify = Callable[[str], Awaitable[None]]


class AIKeyMonitorLoop:
    def __init__(self, monitor: AIKeyHealthMonitor, notify: Notify | None = None, interval: int = 900):
        if interval < 60:
            raise ValueError("AI key monitor interval must be at least 60 seconds")
        self.monitor = monitor
        self.notify = notify
        self.interval = interval
        self._task: asyncio.Task[None] | None = None
        self._previous: dict[str, tuple[bool, tuple[str, ...]]] = {}

    async def run_once(self) -> dict[str, ProviderHealth]:
        results = await self.monitor.check_all()
        notified_transition = False
        for provider, status in results.items():
            models = tuple(getattr(status, "models", ()) or ())
            current = (status.healthy, models)
            previous = self._previous.get(provider)
            if previous is not None and previous != current and self.notify:
                if previous[0] != status.healthy:
                    event = "восстановлен" if status.healthy else "стал недоступен"
                    await self.notify(f"AI: провайдер {provider} {event}.")
                    notified_transition = True
                elif previous[1] != models:
                    await self.notify(f"AI: изменился список моделей провайдера {provider}.")
            self._previous[provider] = current
        if not results:
            return results
        if not any(status.enabled for status in results.values()) and self.notify and not notified_transition:
            await self.notify("AI: нет доступных настроенных провайдеров.")
        return results

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AI key monitor iteration failed")
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="xfi-ai-key-monitor")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
