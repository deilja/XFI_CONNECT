"""Background audit loop; findings are reported through an injected callback."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from bot.services.ai_repo_auditor import AuditReport, RepositoryAuditor

logger = logging.getLogger(__name__)
ReportCallback = Callable[[AuditReport], Awaitable[None]]


class AIAuditLoop:
    def __init__(self, auditor: RepositoryAuditor, report_callback: ReportCallback, interval: int = 3600):
        if interval < 60:
            raise ValueError("audit interval must be at least 60 seconds")
        self.auditor = auditor
        self.report_callback = report_callback
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._last_fingerprint = ""

    async def run_once(self) -> AuditReport:
        report = await asyncio.to_thread(self.auditor.audit)
        if report.fingerprint != self._last_fingerprint:
            self._last_fingerprint = report.fingerprint
            await self.report_callback(report)
        return report

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AI repository audit failed")
            try:
                await asyncio.wait_for(asyncio.sleep(self.interval), timeout=self.interval + 1)
            except asyncio.CancelledError:
                raise

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
