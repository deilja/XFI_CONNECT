"""Small compatibility hook that exposes Crypto Pay in the existing payment menu."""
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.admin_cryptobot import add_cryptobot_button
from bot.keyboards import admin_payments

_original_payments_menu_kb = admin_payments.payments_menu_kb


def payments_menu_kb_with_cryptobot(*args, **kwargs) -> InlineKeyboardMarkup:
    return add_cryptobot_button(_original_payments_menu_kb(*args, **kwargs))


admin_payments.payments_menu_kb = payments_menu_kb_with_cryptobot
