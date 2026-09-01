"""Telegram reporter for read-only AI repository audits."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.ai_repo_auditor import AuditReport


class AIAuditTelegramReporter:
    def __init__(self, bot: Bot, admin_ids: list[int]):
        self.bot = bot
        self.admin_ids = admin_ids

    async def __call__(self, report: AuditReport) -> None:
        if not report.findings:
            return
        lines = [
            "🔎 <b>AI-аудит XFI_CONNECT</b>",
            f"Файлов проверено: <code>{report.files_scanned}</code>",
            f"Проблем найдено: <code>{len(report.findings)}</code>",
            "",
        ]
        for finding in report.findings[:30]:
            lines.append(
                f"<b>{finding.severity.upper()}</b> <code>{finding.path}</code>\n"
                f"{finding.title}: {finding.detail}"
            )
        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Создать AI-задачу", callback_data="xfi_audit:create")
        ]])
        for admin_id in self.admin_ids:
            await self.bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=keyboard)
