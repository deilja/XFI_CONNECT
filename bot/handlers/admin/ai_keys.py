"""Telegram UI for adding and managing AI provider keys."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_IDS
from bot.services.ai_key_manager import AIKeyManager
from bot.services.ai_key_store import AIKeyStore

logger = logging.getLogger(__name__)
router = Router(name="ai_keys")


class AIKeyStates(StatesGroup):
    waiting_key = State()


def _admin(uid: int) -> bool:
    return uid in ADMIN_IDS


def _manager() -> AIKeyManager:
    return AIKeyManager(AIKeyStore("data/ai_keys.enc"))


def _menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Groq", callback_data="aikey:add:groq"), InlineKeyboardButton(text="Grok", callback_data="aikey:add:grok")],
        [InlineKeyboardButton(text="OpenAI", callback_data="aikey:add:openai")],
        [InlineKeyboardButton(text="Статус ключей", callback_data="aikey:status")],
    ])


@router.message(F.text == "/ai_keys")
async def ai_keys(message: Message):
    if not message.from_user or not _admin(message.from_user.id):
        return
    await message.answer("🔐 <b>AI API Keys</b>\n\nКлючи принимаются только в этом административном диалоге и не выводятся обратно.", reply_markup=_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("aikey:add:"))
async def add_key_start(callback: CallbackQuery, state: FSMContext):
    if not _admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    provider = callback.data.split(":")[-1]
    await state.update_data(provider=provider)
    await state.set_state(AIKeyStates.waiting_key)
    await callback.message.answer(f"Введите API key для {provider}. После сохранения ключ не будет показан снова.")
    await callback.answer()


@router.message(AIKeyStates.waiting_key)
async def receive_key(message: Message, state: FSMContext):
    if not message.from_user or not _admin(message.from_user.id) or not message.text:
        return
    data = await state.get_data()
    provider = data.get("provider")
    key = message.text.strip()
    try:
        await message.delete()
    except Exception:
        logger.warning("Could not delete AI key message")
    try:
        ok = await _manager().validate_and_set(provider, key)
        await message.answer("✅ Ключ проверен и сохранён." if ok else "❌ Ключ не прошёл проверку и не сохранён.")
    except Exception:
        logger.exception("AI key setup failed")
        await message.answer("❌ Не удалось проверить/сохранить ключ. Ключ не подтверждён.")
    finally:
        await state.clear()


@router.callback_query(F.data == "aikey:status")
async def key_status(callback: CallbackQuery):
    if not _admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        statuses = _manager().configured()
        text = "\n".join(f"• {name}: {'настроен' if value else 'не настроен'}" for name, value in statuses.items())
        await callback.message.answer("🔐 <b>Статус AI ключей</b>\n" + text, parse_mode="HTML")
    except Exception:
        await callback.message.answer("❌ Хранилище ключей не настроено. Требуется XFI_AI_KEYSTORE_MASTER_KEY.")
    await callback.answer()
