"""Main router of the XFI CONNECT admin panel."""
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.admin import admin_main_menu_kb, marketing_menu_kb, author_support_kb
from bot.services.admin_monitoring import build_admin_summary_text, collect_admin_monitoring_snapshot
from bot.states.admin_states import AdminStates
from bot.utils.admin import is_admin
from bot.utils.text import safe_edit_or_send

logger = logging.getLogger(__name__)
router = Router()


async def get_admin_stats_text() -> str:
    snapshot = await collect_admin_monitoring_snapshot()
    return build_admin_summary_text(snapshot)


@router.callback_query(F.data == "admin_panel")
async def show_admin_panel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    await state.set_state(AdminStates.admin_menu)
    from bot.services.page_context import clear_page_context
    clear_page_context(callback.from_user.id)

    text = await get_admin_stats_text()
    try:
        await safe_edit_or_send(callback.message, text, reply_markup=admin_main_menu_kb())
    except TelegramBadRequest as exc:
        if "is not modified" not in str(exc):
            logger.error("Ошибка при обновлении меню: %s", exc)


@router.callback_query(F.data == "admin_marketing")
async def show_marketing_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await state.set_state(AdminStates.admin_menu)
    await safe_edit_or_send(
        callback.message,
        "📣 <b>Маркетинг</b>\n\nВыберите инструмент:",
        reply_markup=marketing_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_placeholder")
async def admin_placeholder(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer("Скоро будет больше полезных функций")


@router.callback_query(F.data == "admin_author_support")
async def show_author_support(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    text = (
        "🛟 <b>Поддержка XFI CONNECT</b>\n\n"
        "По вопросам работы бота, подписок, ключей, серверов и оплаты "
        "обратитесь в поддержку XFI CONNECT.\n\n"
        "Не передавайте API-ключи, пароли или другие секреты в сообщениях поддержки."
    )
    try:
        await safe_edit_or_send(callback.message, text, reply_markup=author_support_kb())
    except TelegramBadRequest as exc:
        if "is not modified" not in str(exc):
            logger.error("Ошибка при показе поддержки: %s", exc)
