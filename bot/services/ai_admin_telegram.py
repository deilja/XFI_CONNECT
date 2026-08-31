"""Telegram presentation layer for the unified admin AI supervisor."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.services.ai_admin_supervisor import AIAdminSupervisor, TaskStage

router = Router(name="ai_admin_supervisor")
_SUPERVISOR: AIAdminSupervisor | None = None


def configure(supervisor: AIAdminSupervisor) -> None:
    global _SUPERVISOR
    _SUPERVISOR = supervisor


def _keyboard(task_id: str, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Подтвердить", callback_data=f"xfi_ai:approve:{task_id}:{token}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"xfi_ai:reject:{task_id}"),
    ]])


@router.message(Command("ai_task"))
async def ai_task(message: Message) -> None:
    if _SUPERVISOR is None:
        await message.answer("❌ AI Supervisor не настроен.")
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Использование: /ai_task <что нужно сделать>")
        return
    task = _SUPERVISOR.create_task(text)
    choice = task.text
    await message.answer(
        f"🤖 <b>AI Supervisor</b>\n\nID: <code>{task.task_id}</code>\n"
        f"Тип: <code>{task.task_type}</code>\n\nЗапрос:\n{choice}\n\n"
        "Сначала подготовьте план. Самостоятельное выполнение запрещено.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("xfi_ai:approve:"))
async def ai_approve(callback: CallbackQuery) -> None:
    if _SUPERVISOR is None:
        await callback.answer("Supervisor не настроен", show_alert=True)
        return
    _, _, task_id, token = callback.data.split(":", 3)
    try:
        task = _SUPERVISOR.approve(task_id, token)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Задача <code>{task.task_id}</code> подтверждена. Стадия: {task.stage.value}.", parse_mode="HTML")
    except (ValueError, PermissionError) as exc:
        await callback.answer(str(exc), show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("xfi_ai:reject:"))
async def ai_reject(callback: CallbackQuery) -> None:
    if _SUPERVISOR is None:
        await callback.answer("Supervisor не настроен", show_alert=True)
        return
    _, _, task_id = callback.data.split(":", 2)
    try:
        task = _SUPERVISOR._get(task_id)
        if task.stage != TaskStage.WAIT_APPROVAL:
            raise ValueError("Задача уже не ожидает подтверждения")
        task.stage = TaskStage.FAILED
        task.result = "rejected_by_admin"
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"❌ Задача <code>{task.task_id}</code> отклонена.", parse_mode="HTML")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
    await callback.answer()
