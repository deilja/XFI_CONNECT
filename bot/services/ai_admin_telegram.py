"""Telegram entry point for the unified AI admin pipeline."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.services.ai_admin_pipeline import AIAdminPipeline
from bot.services.ai_admin_supervisor import AIAdminSupervisor, TaskStage

router = Router(name="ai_admin_supervisor")
_SUPERVISOR: AIAdminSupervisor | None = None
_PIPELINE: AIAdminPipeline | None = None


def configure(supervisor: AIAdminSupervisor, pipeline: AIAdminPipeline) -> None:
    global _SUPERVISOR, _PIPELINE
    _SUPERVISOR = supervisor
    _PIPELINE = pipeline


def _keyboard(task_id: str, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Подтвердить ChangeSet", callback_data=f"xfi_ai:approve:{task_id}:{token}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"xfi_ai:reject:{task_id}"),
    ]])


@router.message(Command("ai_task"))
async def ai_task(message: Message) -> None:
    if _SUPERVISOR is None or _PIPELINE is None:
        await message.answer("❌ AI Admin Pipeline не настроен.")
        return
    request = message.text.partition(" ")[2].strip()
    if not request:
        await message.answer("Использование: /ai_task <что нужно сделать>")
        return
    task = _SUPERVISOR.create_task(request)
    try:
        pending = await _PIPELINE.prepare(task.task_id, request)
    except Exception:
        task.stage = TaskStage.FAILED
        task.result = "proposal_generation_failed"
        await message.answer("❌ Не удалось подготовить безопасное предложение изменений.")
        return
    await message.answer(
        f"🤖 <b>AI ChangeSet</b>\nID: <code>{task.task_id}</code>\n\n"
        f"<b>Файлы:</b>\n{chr(10).join('• <code>'+c.path+'</code>' for c in pending.changeset.changes)}\n\n"
        f"<b>Preview:</b>\n<pre>{pending.preview[:6000]}</pre>",
        parse_mode="HTML", reply_markup=_keyboard(task.task_id, pending.approval.token),
    )


@router.callback_query(F.data.startswith("xfi_ai:approve:"))
async def ai_approve(callback: CallbackQuery) -> None:
    if _SUPERVISOR is None or _PIPELINE is None:
        await callback.answer("Pipeline не настроен", show_alert=True)
        return
    _, _, task_id, token = callback.data.split(":", 3)
    try:
        _PIPELINE.approve(task_id, token)
        _PIPELINE.begin_transaction(task_id)
        _PIPELINE.apply(task_id)
        task = await _PIPELINE.verify_and_finish(task_id)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ <code>{task.task_id}</code>: <b>{task.stage.value}</b>\n{task.result or ''}", parse_mode="HTML")
    except (ValueError, PermissionError, RuntimeError) as exc:
        await callback.answer(str(exc), show_alert=True)
    except Exception:
        await callback.answer("❌ Ошибка выполнения; изменение не считается успешным.", show_alert=True)


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
        await callback.message.answer(f"❌ ChangeSet <code>{task_id}</code> отклонён.", parse_mode="HTML")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
