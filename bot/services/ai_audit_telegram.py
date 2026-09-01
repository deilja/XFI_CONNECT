"""Telegram reporter for read-only AI repository audits."""
from __future__ import annotations

import secrets

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.ai_audit_tasks import finding_to_task
from bot.services.ai_repo_auditor import AuditFinding, AuditReport
from bot.services.ai_admin_pipeline import AIAdminPipeline
from bot.services.ai_admin_supervisor import AIAdminSupervisor

router = Router(name="ai_audit_tasks")


class AIAuditTelegramReporter:
    def __init__(self, bot: Bot, admin_ids: list[int]):
        self.bot = bot
        self.admin_ids = admin_ids
        self.findings: dict[str, AuditFinding] = {}
        self.supervisor: AIAdminSupervisor | None = None
        self.pipeline: AIAdminPipeline | None = None

    def configure(self, supervisor: AIAdminSupervisor, pipeline: AIAdminPipeline) -> None:
        self.supervisor = supervisor
        self.pipeline = pipeline

    async def __call__(self, report: AuditReport) -> None:
        if not report.findings:
            return
        lines = ["🔎 <b>AI-аудит XFI_CONNECT</b>", f"Файлов: <code>{report.files_scanned}</code>", ""]
        keyboard_rows = []
        for finding in report.findings[:30]:
            finding_id = secrets.token_urlsafe(8)
            self.findings[finding_id] = finding
            lines.append(f"<b>{finding.severity.upper()}</b> <code>{finding.path}</code> — {finding.title}\n{finding.detail}")
            keyboard_rows.append([InlineKeyboardButton(text=f"AI: исправить {finding.path}", callback_data=f"xfi_audit:create:{finding_id}")])
        for admin_id in self.admin_ids:
            await self.bot.send_message(admin_id, "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))


_REPORTER: AIAuditTelegramReporter | None = None


def configure(reporter: AIAuditTelegramReporter, supervisor: AIAdminSupervisor, pipeline: AIAdminPipeline) -> None:
    global _REPORTER
    _REPORTER = reporter
    reporter.configure(supervisor, pipeline)


@router.callback_query(F.data.startswith("xfi_audit:create:"))
async def create_audit_task(callback: CallbackQuery) -> None:
    if _REPORTER is None or _REPORTER.supervisor is None or _REPORTER.pipeline is None:
        await callback.answer("Audit pipeline не настроен", show_alert=True)
        return
    _, _, finding_id = callback.data.split(":", 2)
    finding = _REPORTER.findings.get(finding_id)
    if finding is None:
        await callback.answer("Finding устарел или уже удалён", show_alert=True)
        return
    task_request = finding_to_task(finding)
    task = _REPORTER.supervisor.create_task(task_request.request)
    try:
        pending = await _REPORTER.pipeline.prepare(task.task_id, task_request.request)
    except Exception:
        task.stage = type(task.stage).FAILED
        task.result = "audit_proposal_generation_failed"
        await callback.answer("Не удалось построить ChangeSet", show_alert=True)
        return
    await callback.message.answer(
        f"🤖 <b>AI-задача из аудита</b>\n<code>{task.task_id}</code>\n\n"
        f"<b>{task_request.title}</b>\n\n<pre>{pending.preview[:6000]}</pre>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Подтвердить", callback_data=f"xfi_ai:approve:{task.task_id}:{pending.approval.token}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"xfi_ai:reject:{task.task_id}"),
        ]]),
    )
    await callback.answer("AI-задача подготовлена")
