"""
Диалоговый редактор кода.
/code — войти (или /code задача)
/code_rollback — откат
/code_exit — выход
"""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from bot.services.code_agent import CodeAgent

logger = logging.getLogger(__name__)
router = Router(name="code_editor")
_agents: dict[int, CodeAgent] = {}


class CodeStates(StatesGroup):
    chatting = State()


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _agent(admin_id: int) -> CodeAgent:
    if admin_id not in _agents:
        _agents[admin_id] = CodeAgent()
    return _agents[admin_id]


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Отчёт", callback_data="code:report"),
            InlineKeyboardButton(text="↩️ Rollback", callback_data="code:rollback"),
        ],
        [
            InlineKeyboardButton(text="🗑 Новый чат", callback_data="code:reset"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="code:exit"),
        ],
    ])


@router.message(Command("code"))
async def cmd_code(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    agent = _agent(message.from_user.id)
    await state.set_state(CodeStates.chatting)

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) >= 2:
        wait = await message.answer("🛠 Работаю...")
        try:
            result = await agent.chat(parts[1])
        except Exception as e:
            logger.exception("CodeAgent")
            result = f"❌ {e}"
        try:
            await wait.delete()
        except Exception:
            pass
        await message.answer(result[:4000], reply_markup=_kb(), parse_mode="HTML")
        return

    await message.answer(
        "🛠 <b>Редактор кода</b> (Groq)\n\n"
        "Пиши задачи текстом. Примеры:\n"
        "• покажи bot/handlers\n"
        "• прочитай config.py\n"
        "• исправь ...\n\n"
        "/code_rollback — откат · /code_exit — выход",
        parse_mode="HTML",
        reply_markup=_kb(),
    )


@router.message(Command("code_exit", "code_stop"))
async def cmd_exit(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Вышел из редактора кода.")


@router.message(Command("code_rollback"))
async def cmd_rollback(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(_agent(message.from_user.id).rollback(), reply_markup=_kb())


@router.callback_query(F.data == "code:report")
async def cb_report(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    await callback.message.answer(_agent(callback.from_user.id).report(), parse_mode="HTML", reply_markup=_kb())
    await callback.answer()


@router.callback_query(F.data == "code:rollback")
async def cb_rollback(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    await callback.message.answer(_agent(callback.from_user.id).rollback(), reply_markup=_kb())
    await callback.answer("Rollback")


@router.callback_query(F.data == "code:reset")
async def cb_reset(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    _agent(callback.from_user.id).reset_dialog()
    await state.set_state(CodeStates.chatting)
    await callback.message.answer("Новый чат. История очищена.", reply_markup=_kb())
    await callback.answer()


@router.callback_query(F.data == "code:exit")
async def cb_exit(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    await state.clear()
    await callback.answer()
    try:
        from bot.handlers.admin.main import show_admin_panel
        await show_admin_panel(callback, state)
    except Exception:
        await callback.message.answer("⬅️ Вернуться: открой админку заново.")


@router.message(CodeStates.chatting)
async def on_chat(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id) or not message.text:
        return
    if message.text.strip().lower() in {"выход", "exit", "/start", "/admin"}:
        await state.clear()
        await message.answer("Вышел из редактора кода.")
        return

    agent = _agent(message.from_user.id)
    wait = await message.answer("⏳ ...")
    try:
        result = await agent.chat(message.text)
    except Exception as e:
        logger.exception("CodeAgent")
        result = f"❌ {e}"
    try:
        await wait.delete()
    except Exception:
        pass
    await message.answer(result[:4000], reply_markup=_kb(), parse_mode="HTML")
