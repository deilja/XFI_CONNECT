"""Fail-closed executor bridge for the AI autopilot.

The AI can request an operation, but this module only dispatches to explicitly
registered application operations. No arbitrary shell command, path or Git
remote can be supplied by the model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from bot.services.ai_autopilot import ChangePlan


@dataclass(frozen=True)
class ExecutionResult:
    operation: str
    verified: bool
    message: str


Operation = Callable[[ChangePlan], Awaitable[ExecutionResult]]


class AuditedExecutor:
    def __init__(self) -> None:
        self._operations: dict[str, Operation] = {}

    def register(self, name: str, operation: Operation) -> None:
        if not name or not name.replace("_", "").isalnum():
            raise ValueError("Invalid operation name")
        if name in self._operations:
            raise ValueError(f"Operation already registered: {name}")
        self._operations[name] = operation

    async def execute(self, operation: str, plan: ChangePlan) -> ExecutionResult:
        handler = self._operations.get(operation)
        if handler is None:
            raise PermissionError(f"AI operation is not allowlisted: {operation}")
        result = await handler(plan)
        if not isinstance(result, ExecutionResult):
            raise TypeError("Executor operation must return ExecutionResult")
        if not result.verified:
            raise RuntimeError("Executor reported an unverified result")
        return result

    def operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))
