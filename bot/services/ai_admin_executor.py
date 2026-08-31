"""Guarded executor bridge for AIAdminSupervisor.

The bridge deliberately exposes only an allow-listed, injected implementation.
It does not execute shell commands itself and therefore cannot turn an AI
response into arbitrary command execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

ExecuteFn = Callable[[str, str], Awaitable[str]]
VerifyFn = Callable[[str, str, str], Awaitable[bool]]
RollbackFn = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ExecutionPolicy:
    require_approval: bool = True
    require_verification: bool = True
    allow_rollback: bool = True


class GuardedAIExecutor:
    def __init__(self, execute: ExecuteFn, verify: VerifyFn, rollback: RollbackFn, policy: ExecutionPolicy | None = None):
        self._execute = execute
        self._verify = verify
        self._rollback = rollback
        self.policy = policy or ExecutionPolicy()

    async def execute(self, text: str, plan: str) -> str:
        if self.policy.require_approval is not True:
            raise RuntimeError("unsafe execution policy")
        return await self._execute(text, plan)

    async def verify(self, text: str, plan: str, result: str) -> bool:
        if self.policy.require_verification is not True:
            raise RuntimeError("unsafe verification policy")
        return bool(await self._verify(text, plan, result))

    async def rollback(self, task_id: str) -> None:
        if self.policy.allow_rollback is not True:
            raise RuntimeError("rollback disabled")
        await self._rollback(task_id)
