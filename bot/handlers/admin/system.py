"""
Handlers for the “Bot Settings” section.

Manage updating, stopping the bot and editing texts.
"""
import asyncio
import hashlib
import logging
import os
import sys
from pathlib import Path
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.admin import is_admin
from bot.utils.git_utils import (
    check_git_available,
    get_current_branch,
    get_remote_url,
    check_for_updates,
    pull_updates,
    pull_to_commit,
    force_pull_updates,
    get_last_commit_info,
    get_previous_commits_info,
    install_requirements,
    restart_bot,
)
from bot.version import BOT_COMMIT, BOT_RELEASE
from bot.keyboards.admin import (
    bot_settings_kb,
    bot_mode_toggle_confirm_kb,
    extensions_diagnostics_kb,
    update_confirm_kb,
    update_rollback_entry_kb,
    update_rollback_points_kb,
    update_rollback_confirm_kb,
    force_overwrite_confirm_kb,
    stop_bot_confirm_kb,
    back_and_home_kb,
    admin_logs_menu_kb,
    yadreno_admin_agent_kb,
    yadreno_admin_no_key_kb,
)
from bot.services.yadreno_admin import (
    YADRENO_ADMIN_CHAT_TOPIC_ID,
    YadrenoAdminError,
    YadrenoAdminUpload,
    run_dialog_with_uploads,
)
from bot.services.panel_sync_coordinator import regular_panel_operation
from bot.services.update_rollback import (
    UpdateRollbackError,
    REPOSITORY,
    BRANCH,
    get_current_version_identity,
    get_rollback_point,
    list_rollback_points,
    schedule_admin_rollback,
)
from bot.states.admin_states import AdminStates
from database.requests import get_yadreno_admin_api_key, set_setting

logger = logging.getLogger(__name__)

from bot.utils.text import escape_html, get_message_text_for_storage, safe_edit_or_send
from bot.utils.update_block import is_update_blocked, get_blocked_message, try_unblock, set_update_blocked
from bot.utils.yadreno_admin_errors import format_yadreno_admin_error

router = Router()


def _installed_bot_version_text() -> str:
    """Return the installed release and commit block for update screens."""
    return (
        f"Текущий релиз: <code>{escape_html(BOT_RELEASE)}</code>\n"
        f"Текущий коммит: <code>{escape_html(BOT_COMMIT)}</code>"
    )


_EXTENSION_STATUS_LABELS = {
    'ok': 'найдена',
    'directory_missing': 'папка не создана',
    'not_directory': 'путь не является папкой',
}

_EXTENSION_LOAD_REASON_LABELS = {
    'not_loaded': 'загрузка ещё не выполнялась',
    'disabled': 'загрузка выключена',
    'directory_missing': 'папка не создана',
    'not_directory': 'путь не является папкой',
}

_EXTENSION_REGISTRATION_LABELS = {
    'actions': 'actions',
    'action_policies': 'action policies',
    'guards': 'guards',
    'page_hooks': 'hooks',
    'pricing_policies': 'pricing',
    'promo_reward_policies': 'promo rewards',
    'referral_reward_policies': 'referral rewards',
    'key_lifecycle_hooks': 'key lifecycle',
    'payment_providers': 'payment providers',
    'callback_handlers': 'callbacks',
    'user_access_guards': 'user access',
    'schemas': 'schemas',
    'settings': 'settings',
}

_EXTENSION_UI_TOKENS: dict[str, dict[str, object]] = {}


# ============================================================================
# MAIN SETTINGS MENU
# ============================================================================

@router.callback_query(F.data == "admin_bot_settings")
async def show_bot_settings(callback: CallbackQuery, state: FSMContext):
    """Shows the bot settings menu."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    from bot.services.vpn_api import get_bot_mode
    mode = get_bot_mode()
    if mode == 'subscription':
        mode_label = "📡 Подписка"
        mode_desc = (
            "Бот выдаёт пользователю одну <b>subscription-ссылку</b> — "
            "клиент сам подтягивает все протоколы сервера."
        )
    else:
        mode_label = "🔑 Ключи"
        mode_desc = (
            "Бот создаёт один VLESS/VMess-клиент в одном inbound "
            "и выдаёт ссылку + JSON-конфиг."
        )

    text = (
        "⚙️ <b>Настройки бота</b>\n\n"
        f"<b>Режим работы:</b> {mode_label}\n"
        f"<i>{mode_desc}</i>\n\n"
        "Выберите действие:"
    )

    await safe_edit_or_send(callback.message,
        text,
        reply_markup=bot_settings_kb(mode)
    )
    await callback.answer()


async def _show_bot_mode_confirm(callback: CallbackQuery, target: str):
    """Shows confirmation of switching the bot's operating mode."""
    if target == 'subscription':
        warning = (
            "⚠️ <b>Переключение в режим Подписка</b>\n\n"
            "При ближайших синхронизациях (≈раз в 30 минут) бот:\n"
            "• создаст клиентов во всех inbound каждого сервера для существующих ключей "
            "(с единым subId и email);\n"
            "• новые ключи будут выдаваться как <b>subscription URL</b>.\n\n"
            "Текущие пользователи продолжат работать со старыми ссылками "
            "до их замены или продления.\n\n"
            "Продолжить?"
        )
    else:
        warning = (
            "⚠️ <b>Переключение в режим Ключи</b>\n\n"
            "При ближайших синхронизациях бот:\n"
            "• оставит на каждом сервере по одному клиенту (в inbound с минимальным id) "
            "на каждый ключ;\n"
            "• остальных клиентов с тем же email — <b>удалит</b>;\n"
            "• новые ключи будут выдаваться как одна VLESS/VMess-ссылка.\n\n"
            "<b>Subscription URL у пользователей перестанут работать.</b>\n\n"
            "Продолжить?"
        )

    await safe_edit_or_send(callback.message, warning,
                            reply_markup=bot_mode_toggle_confirm_kb(target))
    await callback.answer()


@router.callback_query(F.data == "admin_extensions_diagnostics")
async def show_extensions_diagnostics(callback: CallbackQuery, state: FSMContext):
    """Shows diagnostics and loader controls for custom extensions."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await _render_extensions_diagnostics_screen(callback.message)
    await callback.answer()


@router.callback_query(F.data.in_({"admin_extensions_set:0", "admin_extensions_set:1"}))
async def set_extensions_loading(callback: CallbackQuery, state: FSMContext):
    """Persists the custom extension loader state for the next bot start."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    target_enabled = callback.data.rsplit(':', 1)[1] == '1'
    from bot.utils.custom_extensions import CUSTOM_EXTENSIONS_ENABLED_SETTING

    set_setting(CUSTOM_EXTENSIONS_ENABLED_SETTING, '1' if target_enabled else '0')
    logger.info(
        "Custom extension loading %s by admin %s; applies on next bot start",
        'enabled' if target_enabled else 'disabled',
        callback.from_user.id,
    )
    await _render_extensions_diagnostics_screen(callback.message)
    await callback.answer("Настройка сохранена. Применится после перезапуска бота.")


async def _render_extensions_diagnostics_screen(message: Message) -> None:
    """Renders the current custom extension diagnostics in one message."""
    from bot.utils.custom_extensions import get_custom_extensions_diagnostics

    diagnostics = get_custom_extensions_diagnostics()
    await safe_edit_or_send(
        message,
        _format_extensions_diagnostics(diagnostics),
        reply_markup=extensions_diagnostics_kb(
            bool(diagnostics.get('enabled')),
            _extension_settings_menu_buttons(diagnostics),
        ),
    )


def _format_extensions_diagnostics(diagnostics: dict) -> str:
    enabled = bool(diagnostics.get('enabled'))
    status_icon = '🟢' if enabled else '⚪'
    directory = Path(str(diagnostics.get('directory') or 'custom_extensions'))
    directory_label = _EXTENSION_STATUS_LABELS.get(
        str(diagnostics.get('directory_status') or ''),
        'неизвестно',
    )

    last_load = diagnostics.get('last_load') or {}
    loaded = list(last_load.get('loaded') or [])
    failed = dict(last_load.get('failed') or {})
    skipped = bool(last_load.get('skipped'))
    reason = str(last_load.get('reason') or '')
    reason_label = _EXTENSION_LOAD_REASON_LABELS.get(reason, reason or 'выполнена')

    files = list(diagnostics.get('files') or [])
    candidates = sum(1 for item in files if item.get('status') == 'candidate')
    invalid = sum(1 for item in files if item.get('status') == 'invalid_filename')
    ignored = sum(1 for item in files if item.get('status') == 'ignored_private')

    lines = [
        "🧩 <b>Диагностика расширений</b>",
        "",
        f"<b>Загрузка:</b> {status_icon} {'включена' if enabled else 'выключена'}",
        f"<b>Папка:</b> <code>{escape_html(directory.name)}</code> — {escape_html(directory_label)}",
        f"<b>Последняя загрузка:</b> {escape_html(reason_label) if skipped else 'выполнена'}",
        f"<b>Файлы:</b> {len(files)} всего, {candidates} к загрузке, {invalid} с ошибкой имени, {ignored} приватных",
        f"<b>Итог:</b> {len(loaded)} загружено, {len(failed)} с ошибками",
    ]

    if loaded:
        lines.append("<b>Загружено:</b> " + ", ".join(escape_html(str(item)) for item in loaded[:20]))
    if failed:
        lines.append("<b>Ошибки:</b>")
        for name, error in list(failed.items())[:10]:
            lines.append(f"• <code>{escape_html(str(name))}</code>: {escape_html(str(error))}")
    if len(files) > 20:
        lines.append(f"<i>…и ещё {len(files) - 20} файлов.</i>")
    return "\n".join(lines)


# The remainder of this module is intentionally kept unchanged by this
# migration. Update/rollback handlers below are repository-bound through the
# XFI CONNECT compatibility layer.
