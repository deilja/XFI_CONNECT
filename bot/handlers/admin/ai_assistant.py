"""AI-ассистент админ-панели XFI CONNECT.

AI contract: this module is the Telegram UI only. Business logic belongs in
services; privileged actions must keep existing admin authorization and must
not be executed merely because the model suggested them.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

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
        default_provider = getattr(config, "AI_DEFAULT_PROVIDER", "groq")
        _agents[admin_id] = AIAgent(provider=default_provider)
    return _agents[admin_id]


def _ai_keyboard(provider: str) -> InlineKeyboardMarkup:
    groq_mark = "✅ " if provider == "groq" else ""
    grok_mark = "✅ " if provider == "grok" else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"{groq_mark}Groq", callback_data="ai:provider:groq"),
            InlineKeyboardButton(text=f"{grok_mark}Grok", callback_data="ai:provider:grok"),
        ],
        [
            InlineKeyboardButton(text="🗑 Новый чат", callback_data="ai:reset"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="ai:exit"),
        ],
    ])


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("ai", "groq", "grok"))
async def cmd_ai(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    agent = _get_agent(message.from_user.id)
    await state.set_state(AIStates.chatting)
    await message.answer(
        "🤖 <b>AI Ассистент</b>\n\n"
        f"Текущий провайдер: <b>{agent.provider.upper()}</b>\n\n"
        "Пиши запросы обычным текстом.\n"
        "• «покажи статус серверов»\n"
        "• «статистика ключей»\n"
        "• «продли ключ 15 на 30 дней»",
        reply_markup=_ai_keyboard(agent.provider),
        parse_mode="HTML",
    )


@router.callback_query(F.data.in_({"ai:open", "admin_ai_assistant", "admin_ai"}))
async def cb_ai_open(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    agent = _get_agent(callback.from_user.id)
    await state.set_state(AIStates.chatting)
    await callback.message.edit_text(
        "🤖 <b>AI Ассистент</b>\n\n"
        f"Текущий провайдер: <b>{agent.provider.upper()}</b>\n\n"
        "Пиши запросы обычным текстом.",
        reply_markup=_ai_keyboard(agent.provider),
        parse_mode="HTML",
    )
    await callback.answer()


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
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("ai:provider:"))
async def cb_provider(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    provider = callback.data.split(":", 2)[-1]
    if provider not in {"groq", "grok"}:
        await callback.answer("Неподдерживаемый AI-провайдер", show_alert=True)
        return
    agent = _get_agent(callback.from_user.id)
    try:
        agent.set_provider(provider)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.set_state(AIStates.chatting)
    await callback.message.edit_text(
        "🤖 <b>AI Ассистент</b>\n\n"
        f"Провайдер переключён на: <b>{provider.upper()}</b>\n"
        "История чата очищена.\n\nПиши запросы.",
        reply_markup=_ai_keyboard(provider),
        parse_mode="HTML",
    )
    await callback.answer(f"Провайдер: {provider.upper()}")


@router.callback_query(F.data == "ai:reset")
async def cb_reset(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    agent = _get_agent(callback.from_user.id)
    agent.reset()
    await state.set_state(AIStates.chatting)
    await callback.message.edit_text(
        "🤖 <b>AI Ассистент</b>\n\n"
        "Чат очищен.\n"
        f"Провайдер: <b>{agent.provider.upper()}</b>\n\nПиши новый запрос.",
        reply_markup=_ai_keyboard(agent.provider),
        parse_mode="HTML",
    )
    await callback.answer("Чат очищен")


@router.message(AIStates.chatting)
async def process_ai_message(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text:
        await message.answer("Пока понимаю только текст.")
        return
    if message.text.strip().lower() in {"/start", "/admin", "назад", "выход", "exit"}:
        await state.clear()
        await message.answer("Вышел из AI-ассистента.")
        return

    agent = _get_agent(message.from_user.id)
    wait_msg = await message.answer("⏳ Думаю...")
    try:
        answer = await agent.chat(
            message.text,
            role="bot/handlers/admin/ai_assistant.py — Telegram admin AI UI; do not execute privileged actions without explicit existing authorization/workflow",
        )
    except Exception:
        logger.exception("AI error")
        answer = "❌ Ошибка AI. Подробности записаны в журнал."
    try:
        await wait_msg.delete()
    except Exception:
        pass
    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n… (обрезано)"
    try:
        await message.answer(answer, reply_markup=_ai_keyboard(agent.provider), parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer(answer, reply_markup=_ai_keyboard(agent.provider), parse_mode=None)
