"""
Main router of the admin panel.
"""
import logging
import asyncio
from aiogram import Router, F
from aiogram.types import CallbackQuery, ReplyKeyboardRemove, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.services.admin_monitoring import (
    build_admin_summary_text,
    collect_admin_monitoring_snapshot,
)
from bot.services.code_agent import CodeAgent
from bot.states.admin_states import AdminStates
from bot.keyboards.admin import (
    admin_main_menu_kb, 
    author_support_kb, 
    marketing_menu_kb,
    cancel_code_agent_kb,
    rollback_code_kb
)
from bot.utils.admin import is_admin
from bot.utils.telegram_links import build_telegram_link
from bot.utils.text import safe_edit_or_send

logger = logging.getLogger(__name__)

router = Router()
code_agent = CodeAgent()


# ============================================================================
# ADMIN MAIN MENU
# ============================================================================

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

    text = await get_admin_stats_text()
    
    try:
        await safe_edit_or_send(
            callback.message, 
            text,
            reply_markup=admin_main_menu_kb()
        )
    except TelegramBadRequest as e:
        if "is not modified" not in str(e):
            logger.error(f"Ошибка при обновлении меню: {e}")


# ============================================================================
# DEV AGENT / INTERACTIVE CODE EDITING SECTION
# ============================================================================

@router.callback_query(F.data == "admin_code_agent")
async def start_code_agent_interactive(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    await state.set_state(AdminStates.waiting_for_code_task)

    text = (
        "🤖 <b>ИИ DevAgent — Интерактивный режим</b>\n\n"
        "Отправьте текстом задачу по редактированию или улучшению кода бота.\n\n"
        "<i>Пример: Добавь команду /server_status, высылающую нагрузку на CPU и RAM.</i>"
    )

    await safe_edit_or_send(
        callback.message,
        text,
        reply_markup=cancel_code_agent_kb()
    )


@router.callback_query(F.data == "admin_code_cancel")
async def cancel_code_agent(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.admin_menu)
    await callback.answer("Действие отменено")
    await show_admin_panel(callback, state)


@router.message(AdminStates.waiting_for_code_task)
async def process_code_task_input(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    task_text = message.text.strip() if message.text else ""
    if not task_text:
        await message.answer("⚠️ Пожалуйста, отправьте текстовое описание задачи.")
        return

    await state.set_state(AdminStates.admin_menu)

    status_msg = await message.answer("🤖 <i>DevAgent запущен: считывает файлы, пишет код и тестирует...</i>")

    result = await code_agent.execute_task(task_text)

    await safe_edit_or_send(
        status_msg, 
        f"🛠 <b>Результат работы DevAgent:</b>\n\n{result}"
    )


@router.message(Command("code"))
async def handle_code_command(message: Message):
    """Быстрый вызов через команду /code <задача>"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    task = message.text.replace("/code", "").strip()
    if not task:
        await message.answer(
            "🛠 <b>ИИ DevAgent (с авто-откатом)</b>\n\n"
            "Использование: <code>/code &lt;описание задачи&gt;</code>\n\n"
            "<b>Пример:</b>\n"
            "<code>/code Добавь команду /ping, которая отвечает 'Pong!'</code>"
        )
        return

    status_msg = await message.answer("🤖 <i>Агент анализирует код и выполняет задачу...</i>")

    result = await code_agent.execute_task(task)

    await safe_edit_or_send(
        status_msg, 
        f"🛠 <b>Результат работы DevAgent:</b>\n\n{result}"
    )


# ============================================================================
# MARKETING & SUPPORT SECTIONS
# ============================================================================

@router.callback_query(F.data == "admin_marketing")
async def show_marketing_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await state.set_state(AdminStates.admin_menu)
    text = "📣 <b>Маркетинг</b>\n\nВыберите инструмент:"
    await safe_edit_or_send(callback.message, text, reply_markup=marketing_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_author_support")
async def show_author_support(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
        
    await callback.answer()
    developer_link = build_telegram_link('plushkin_blog')
    seller_link = build_telegram_link('Ya_SellerBot', 'item-40')
    
    text = (
        "👤 <b>Автор и поддержка</b>\n\n"
        f"<b>Разработчик</b>: <a href=\"{developer_link}\">Plushkin Blog</a>\n\n"
        "Я собираю деньги на разработку игры в жанре MMORTS с честной экономикой.\n\n"
        "💳 <b>Карты РФ</b>: https://yoomoney.ru/fundraise/1GJ73GGRJBC.260318\n"
        f"💰 <b>USDT (TON/BSC/ARBITRUM)</b>: {seller_link}"
    )
    
    await safe_edit_or_send(callback.message, text, reply_markup=author_support_kb())
