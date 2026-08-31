"""Telegram UI for the end-to-end ChangeSet workflow."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.services.ai_admin_workflow import AIAdminWorkflow
from bot.services.ai_changeset_bridge import ProposedChange

router = Router(name="ai_admin_workflow")
_WORKFLOW: AIAdminWorkflow | None = None


def configure(workflow: AIAdminWorkflow) -> None:
    global _WORKFLOW
    _WORKFLOW = workflow


def _approval_keyboard(task_id: str, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Подтвердить ChangeSet", callback_data=f"xfi_cs:approve:{task_id}:{token}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"xfi_cs:reject:{task_id}"),
    ]])


def format_preview(pending) -> str:
    changes = pending.changeset.changes
    lines = ["🤖 <b>Предложение AI</b>", f"ID: <code>{pending.task_id}</code>", "", "<b>Изменяемые файлы:</b>"]
    for change in changes:
        lines.append(f"• <code>{change.path}</code> — SHA {change.old_sha256[:12]}")
    lines.extend(["", "<b>План:</b>", pending.preview, "", "Подтвердите ChangeSet для применения."])
    return "\n".join(lines)


@router.callback_query(F.data.startswith("xfi_cs:approve:"))
async def approve_changeset(callback: CallbackQuery) -> None:
    if _WORKFLOW is None:
        await callback.answer("Workflow не настроен", show_alert=True)
        return
    _, _, task_id, token = callback.data.split(":", 3)
    try:
        _WORKFLOW.approve(task_id, token)
        _WORKFLOW.begin_transaction(task_id)
        _WORKFLOW.apply(task_id)
        task = await _WORKFLOW.verify_and_finish(task_id)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"Задача <code>{task.task_id}</code>: <b>{task.stage.value}</b>\n{task.result}", parse_mode="HTML")
    except (ValueError, PermissionError, RuntimeError) as exc:
        await callback.answer(str(exc), show_alert=True)
    except Exception:
        await callback.answer("Ошибка выполнения; состояние задачи сохранено", show_alert=True)


@router.callback_query(F.data.startswith("xfi_cs:reject:"))
async def reject_changeset(callback: CallbackQuery) -> None:
    if _WORKFLOW is None:
        await callback.answer("Workflow не настроен", show_alert=True)
        return
    _, _, task_id = callback.data.split(":", 2)
    try:
        task = _WORKFLOW.supervisor._get(task_id)
        if task.stage.value != "wait_approval":
            raise ValueError("ChangeSet уже нельзя отклонить")
        task.stage = type(task.stage).FAILED
        task.result = "rejected_by_admin"
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"❌ ChangeSet <code>{task_id}</code> отклонён.", parse_mode="HTML")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
