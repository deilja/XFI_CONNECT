"""Unified admin AI supervisor: plan, approve, execute, verify, rollback.

The supervisor is policy-driven. Analysis is read-only; mutations require an
explicit admin approval token created by this module.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from bot.services.ai_task_router import AITaskRouter


class TaskStage(str, Enum):
    ANALYZE = "analyze"
    PLAN = "plan"
    WAIT_APPROVAL = "wait_approval"
    EXECUTE = "execute"
    VERIFY = "verify"
    ROLLBACK = "rollback"
    DONE = "done"
    FAILED = "failed"


@dataclass
class AdminTask:
    task_id: str
    text: str
    task_type: str
    stage: TaskStage
    plan: str = ""
    approval_token: str | None = None
    created_at: float = field(default_factory=time.time)
    result: str = ""


class AIAdminSupervisor:
    """Single control plane for natural-language admin requests."""

    def __init__(self, router: AITaskRouter, executor: Any | None = None):
        self.router = router
        self.executor = executor
        self.tasks: dict[str, AdminTask] = {}

    def create_task(self, text: str) -> AdminTask:
        routed = self.router.route(text)
        task_id = hashlib.sha256(f"{time.time_ns()}:{text}".encode()).hexdigest()[:12]
        task = AdminTask(task_id, routed.text, routed.task_type, TaskStage.ANALYZE)
        self.tasks[task_id] = task
        return task

    def set_plan(self, task_id: str, plan: str) -> AdminTask:
        task = self._get(task_id)
        if task.stage not in {TaskStage.ANALYZE, TaskStage.PLAN}:
            raise ValueError("План нельзя изменить на текущем этапе")
        task.plan = (plan or "").strip()
        if not task.plan:
            raise ValueError("Пустой план")
        task.approval_token = hashlib.sha256(f"{task.task_id}:{task.plan}".encode()).hexdigest()[:16]
        task.stage = TaskStage.WAIT_APPROVAL
        return task

    def approve(self, task_id: str, token: str) -> AdminTask:
        task = self._get(task_id)
        if task.stage != TaskStage.WAIT_APPROVAL or token != task.approval_token:
            raise PermissionError("Недействительное подтверждение")
        task.stage = TaskStage.EXECUTE
        return task

    async def execute(self, task_id: str) -> AdminTask:
        task = self._get(task_id)
        if task.stage != TaskStage.EXECUTE:
            raise ValueError("Задача не подтверждена")
        if self.executor is None:
            task.stage = TaskStage.FAILED
            task.result = "Executor не настроен"
            return task
        try:
            task.result = await self.executor.execute(task.text, task.plan)
            task.stage = TaskStage.VERIFY
        except Exception as exc:
            task.result = f"execution_failed:{type(exc).__name__}"
            task.stage = TaskStage.FAILED
        return task

    async def verify(self, task_id: str) -> AdminTask:
        task = self._get(task_id)
        if task.stage != TaskStage.VERIFY:
            raise ValueError("Задача не готова к проверке")
        verifier = getattr(self.executor, "verify", None)
        if verifier is None:
            task.stage = TaskStage.FAILED
            task.result += "\nverification_not_configured"
            return task
        try:
            ok = bool(await verifier(task.text, task.plan, task.result))
            task.stage = TaskStage.DONE if ok else TaskStage.ROLLBACK
        except Exception as exc:
            task.result += f"\nverification_failed:{type(exc).__name__}"
            task.stage = TaskStage.ROLLBACK
        return task

    async def rollback(self, task_id: str) -> AdminTask:
        task = self._get(task_id)
        if task.stage != TaskStage.ROLLBACK:
            raise ValueError("Rollback не требуется")
        rollback = getattr(self.executor, "rollback", None)
        if rollback is None:
            task.stage = TaskStage.FAILED
            task.result += "\nrollback_not_configured"
            return task
        await rollback(task.task_id)
        task.stage = TaskStage.FAILED
        return task

    def _get(self, task_id: str) -> AdminTask:
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise ValueError("Задача не найдена") from exc
