from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def cryptobot_management_kb(enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🟢 Включено", callback_data="admin_cryptobot_mgmt_set:1"),
        InlineKeyboardButton(text="⚪ Выключено", callback_data="admin_cryptobot_mgmt_set:0"),
    )
    builder.row(InlineKeyboardButton(text="🔐 Изменить API-токен", callback_data="admin_cryptobot_mgmt_edit_token"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_payments"), InlineKeyboardButton(text="🏠 Главная", callback_data="admin_panel"))
    return builder.as_markup()


def add_cryptobot_button(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Append Crypto Pay to the existing payment menu without replacing old providers."""
    rows = list(markup.inline_keyboard or [])
    if not any(any(getattr(button, "callback_data", "") == "admin_payments_cryptobot" for button in row) for row in rows):
        rows.insert(max(0, len(rows) - 1), [InlineKeyboardButton(text="💎 Crypto Pay", callback_data="admin_payments_cryptobot")])
    markup.inline_keyboard = rows
    return markup
