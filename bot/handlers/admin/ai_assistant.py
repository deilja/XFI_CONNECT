"""
AI-ассистент для админ-панели YadrenoVPN / XFI_CONNECT.
Поддерживает DeepSeek и Grok.
"""
from __future__ import annotations

import logging
import html
from typing import Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

import config
from config import ADMIN_IDS
from bot.services.ai_agent import AIAgent

logger = logging.getLogger(__name__)
router = Router(name="ai_assistant")

_agents: dict[int, AIAgent] = {}


class AIStates(StatesGroup):
    chatting = State()


def _get_agent(admin_id: int) -> AIAgent:
    if admin_id not in _agents:
        default_provider = getattr(config, "AI_DEFAULT_PROVIDER", "deepseek")
        _agents[admin_id] = AIAgent(provider=default_provider)
    return _agents[admin_id]


def _ai_keyboard(provider: str) -> InlineKeyboardMarkup:
    ds_mark = "✅ " if provider == "deepseek" else ""
    grok_mark = "✅ " if provider == "grok" else ""

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"{ds_mark}DeepSeek",
                callback_data="ai:provider:deepseek"
            ),
            InlineKeyboardButton(
                text=f"{grok_mark}Grok",
                callback_data="ai:provider:grok"
            ),
        ],
        [
            InlineKeyboardButton(text="🗑 Новый чат", callback_data="ai:reset"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="ai:exit"),
        ],
    ])


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ====================== ВХОД ======================

@router.message(Command("ai", "deepseek", "grok"))
async def cmd_ai(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    agent = _get_agent(message.from_user.id)
    await state.set_state(AIStates.chatting)

    text = (
        f"🤖 <b>AI Ассистент</b>\n\n"
        f"Текущая модель: <b>{agent.provider.upper()}</b>\n\n"
        f"Можешь писать обычным текстом:\n"
        f"• «покажи статус серверов»\n"
        f"• «статистика ключей»\n"
        f"• «продли ключ 15 на 30 дней»\n"
    )
    await message.answer(text, reply_markup=_ai_keyboard(agent.provider), parse_mode="HTML")


@router.callback_query(F.data.in_({"ai:open", "admin_ai_assistant", "admin_ai"}))
async def cb_ai_open(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    agent = _get_agent(callback.from_user.id)
    await state.set_state(AIStates.chatting)

    text = (
        f"🤖 <b>AI Ассистент</b>\n\n"
        f"Текущая модель: <b>{agent.provider.upper()}</b>\n\n"
        f"Пиши запросы обычным текстом."
    )
    await callback.message.edit_text(
        text,
        reply_markup=_ai_keyboard(agent.provider),
        parse_mode="HTML",
    )
    await callback.answer()


# ====================== ВЫХОД ИЗ АССИСТЕНТА ======================

@router.callback_query(F.data.in_({"ai:exit", "admin:main"}))
async def cb_ai_exit(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer("Вышли из AI-ассистента")

    try:
        from bot.handlers.admin.main import show_admin_panel
        await show_admin_panel(callback, state)
    except Exception:
        await callback.message.edit_text(
            "◀️ <b>Вы вышли из AI-ассистента.</b>\n\nОтправьте /admin для открытия главного меню.",
            parse_mode="HTML"
        )


# ====================== ПЕРЕКЛЮЧЕНИЕ МОДЕЛИ ======================

@router.callback_query(F.data.startswith("ai:provider:"))
async def cb_provider(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    provider = callback.data.split(":")[-1]
    agent = _get_agent(callback.from_user.id)
    agent.set_provider(provider)

    await state.set_state(AIStates.chatting)
    await callback.message.edit_text(
        f"🤖 <b>AI Ассистент</b>\n\n"
        f"Модель переключена на: <b>{provider.upper()}</b>\n"
        f"История чата очищена.\n\n"
        f"Пиши запросы.",
        reply_markup=_ai_keyboard(provider),
        parse_mode="HTML",
    )
    await callback.answer(f"Модель: {provider.upper()}")


# ====================== НОВЫЙ ЧАТ ======================

@router.callback_query(F.data == "ai:reset")
async def cb_reset(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    agent = _get_agent(callback.from_user.id)
    agent.reset()

    await state.set_state(AIStates.chatting)
    await callback.message.edit_text(
        f"🤖 <b>AI Ассистент</b>\n\n"
        f"Чат очищен.\n"
        f"Модель: <b>{agent.provider.upper()}</b>\n\n"
        f"Пиши новый запрос.",
        reply_markup=_ai_keyboard(agent.provider),
        parse_mode="HTML",
    )
    await callback.answer("Чат очищен")


# ====================== ОБРАБОТКА СООБЩЕНИЙ ======================

@router.message(AIStates.chatting)
async def process_ai_message(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    if not message.text:
        await message.answer("Пока понимаю только текст.")
        return

    text_lower = message.text.strip().lower()
    if text_lower in {"/start", "/admin", "назад", "выход", "exit"}:
        await state.clear()
        await message.answer("Вышел из AI-ассистента.")
        return

    agent = _get_agent(message.from_user.id)
    wait_msg = await message.answer("⏳ Думаю...")

    try:
        answer = await agent.chat(message.text)
    except Exception as e:
        logger.exception("AI error")
        answer = f"❌ Ошибка: {e}"

    try:
        await wait_msg.delete()
    except Exception:
        pass

    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n… (обрезано)"

    try:
        await message.answer(
            answer,
            reply_markup=_ai_keyboard(agent.provider),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await message.answer(
            answer,
            reply_markup=_ai_keyboard(agent.provider),
            parse_mode=None
        )
