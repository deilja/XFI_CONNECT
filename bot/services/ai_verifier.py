"""Deterministic verification hooks for AI ChangeSets.

No shell commands are accepted from the model. The application may register
its own safe checks (tests, import checks, health checks) explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable


Check = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


class VerificationPipeline:
    def __init__(self) -> None:
        self._checks: list[tuple[str, Check]] = []

    def register(self, name: str, check: Check) -> None:
        if not name or any(existing == name for existing, _ in self._checks):
            raise ValueError(f"Invalid or duplicate verification check: {name!r}")
        self._checks.append((name, check))

    async def run(self) -> tuple[bool, tuple[CheckResult, ...]]:
        results: list[CheckResult] = []
        for name, check in self._checks:
            try:
                passed = bool(await check())
                results.append(CheckResult(name, passed))
            except Exception as exc:
                results.append(CheckResult(name, False, f"{type(exc).__name__}: {exc}"))
        return bool(results) and all(item.passed for item in results), tuple(results)

    def checks(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self._checks)
