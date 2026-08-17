"""Administrator controls for Crypto Pay."""
from __future__ import annotations

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database.db_cryptobot import get_cryptobot_token, is_cryptobot_enabled, set_cryptobot_enabled, set_cryptobot_token
from bot.keyboards.admin import back_and_home_kb
from bot.keyboards.admin_cryptobot import cryptobot_management_kb
from bot.services.cryptobot import validate_cryptobot_token, cryptobot_lifecycle_lock
from bot.states.admin_states import AdminStates
from bot.utils.admin import is_admin
from bot.utils.text import escape_html, get_message_text_for_storage, safe_edit_or_send

logger = logging.getLogger(__name__)
router = Router()


class CryptoBotStates(StatesGroup):
    setup_token = State()


def _masked(token: str) -> str:
    if not token:
        return "❌ Не задан"
    if len(token) < 12:
        return "Установлен ✅"
    return f"Установлен ✅ (<code>{escape_html(token[:6])}...{escape_html(token[-4:])}</code>)"


async def _render(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminStates.payments_menu)
    enabled = is_cryptobot_enabled()
    text = (
        "💎 <b>Crypto Pay (@CryptoBot)</b>\n\n"
        "Оплата создаётся через официальный Crypto Pay API. Поддерживаются RUB и USD.\n"
        "Счёт действует 60 минут. Webhook не требуется — бот проверяет статус счета.\n\n"
        f"{'🟢' if enabled else '⚪'} Статус: <b>{'включено' if enabled else 'выключено'}</b>\n"
        f"🔐 API-токен: {_masked(get_cryptobot_token())}\n\n"
        "Выберите действие:"
    )
    await safe_edit_or_send(message, text, reply_markup=cryptobot_management_kb(enabled), show_web_page_preview=False)


@router.callback_query(F.data == "admin_payments_cryptobot")
async def show_cryptobot_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await _render(callback.message, state)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cryptobot_mgmt_set:"))
async def toggle_cryptobot(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    target = callback.data.rsplit(":", 1)[1] == "1"
    if target:
        token = get_cryptobot_token()
        if not token:
            await callback.answer("❌ Сначала задайте API-токен", show_alert=True)
            return
        try:
            await validate_cryptobot_token(token)
        except Exception:
            await callback.answer("❌ Crypto Pay не подтвердил токен", show_alert=True)
            return
    async with cryptobot_lifecycle_lock():
        set_cryptobot_enabled(target)
    await callback.answer("Crypto Pay включён" if target else "Crypto Pay выключен")
    await _render(callback.message, state)


@router.callback_query(F.data == "admin_cryptobot_mgmt_edit_token")
async def edit_cryptobot_token(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await state.set_state(CryptoBotStates.setup_token)
    await safe_edit_or_send(
        callback.message,
        "🔐 <b>Введите API-токен Crypto Pay</b>\n\n"
        "@CryptoBot → Crypto Pay → My Apps → Create App.\n\n"
        "Сообщение с токеном будет удалено после получения.",
        reply_markup=back_and_home_kb("admin_payments_cryptobot"),
    )
    await callback.answer()


@router.message(CryptoBotStates.setup_token)
async def save_cryptobot_token(message: Message, state: FSMContext):
    token = get_message_text_for_storage(message, "plain").strip()
    try:
        await message.delete()
    except Exception:
        pass
    if not token or any(ord(c) < 32 for c in token):
        await safe_edit_or_send(message, "❌ Некорректный токен.", reply_markup=back_and_home_kb("admin_payments_cryptobot"))
        return
    try:
        await validate_cryptobot_token(token)
    except Exception as error:
        logger.warning("Crypto Pay token validation failed: %s", error)
        await safe_edit_or_send(message, "❌ Crypto Pay не подтвердил этот токен.", reply_markup=back_and_home_kb("admin_payments_cryptobot"))
        return
    async with cryptobot_lifecycle_lock():
        set_cryptobot_token(token)
        set_cryptobot_enabled(True)
    await _render(message, state)
