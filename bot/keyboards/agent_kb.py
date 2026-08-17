"""Inline-кнопки Local YaAdmin / DevAgent."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def agent_home_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="ag:cat:stats"),
        InlineKeyboardButton(text="🖥️ Серверы", callback_data="ag:cat:servers"),
    )
    b.row(
        InlineKeyboardButton(text="🔑 Ключи", callback_data="ag:cat:keys"),
        InlineKeyboardButton(text="👥 Юзеры", callback_data="ag:cat:users"),
    )
    b.row(
        InlineKeyboardButton(text="📄 Страницы", callback_data="ag:cat:pages"),
        InlineKeyboardButton(text="💳 Тарифы", callback_data="ag:cat:tariffs"),
    )
    b.row(
        InlineKeyboardButton(text="🎟 Промо", callback_data="ag:cat:promo"),
        InlineKeyboardButton(text="📡 Панель 3X", callback_data="ag:cat:panel"),
    )
    b.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="ag:cat:broadcast"),
        InlineKeyboardButton(text="📋 Логи", callback_data="ag:act:logs"),
    )
    b.row(
        InlineKeyboardButton(text="🛠 Код", callback_data="ag:cat:code"),
        InlineKeyboardButton(text="💬 Свободный чат", callback_data="ag:chat"),
    )
    b.row(
        InlineKeyboardButton(text="📋 Отчёт", callback_data="code:report"),
        InlineKeyboardButton(text="↩️ Rollback", callback_data="code:rollback"),
    )
    b.row(
        InlineKeyboardButton(text="🗑 Новый чат", callback_data="code:reset"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="code:exit"),
    )
    return b.as_markup()


def agent_back_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⬅️ В меню агента", callback_data="ag:home"))
    return b.as_markup()


def agent_stats_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔑 Статистика ключей", callback_data="ag:act:keys_stats"))
    b.row(InlineKeyboardButton(text="👥 Статистика юзеров", callback_data="ag:act:users_stats"))
    b.row(InlineKeyboardButton(text="⏰ Истекают за 3 дня", callback_data="ag:act:expiring_3"))
    b.row(InlineKeyboardButton(text="⏰ Истекают за 7 дней", callback_data="ag:act:expiring_7"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_servers_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📋 Список серверов", callback_data="ag:act:servers"))
    b.row(InlineKeyboardButton(text="❤️ Healthcheck панелей", callback_data="ag:act:panel_health"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_keys_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📊 Стата ключей", callback_data="ag:act:keys_stats"))
    b.row(InlineKeyboardButton(text="🔎 Ключ по ID…", callback_data="ag:ask:key_id"))
    b.row(InlineKeyboardButton(text="👤 Ключи юзера (tg id)…", callback_data="ag:ask:user_keys"))
    b.row(InlineKeyboardButton(text="➕ Продлить ключ…", callback_data="ag:ask:extend_key"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_users_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📊 Стата юзеров", callback_data="ag:act:users_stats"))
    b.row(InlineKeyboardButton(text="🔎 Юзер по tg id…", callback_data="ag:ask:user_id"))
    b.row(InlineKeyboardButton(text="🔎 Юзер по @username…", callback_data="ag:ask:username"))
    b.row(InlineKeyboardButton(text="💰 Баланс…", callback_data="ag:ask:balance"))
    b.row(InlineKeyboardButton(text="💳 Оплаты юзера…", callback_data="ag:ask:payments"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_pages_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📋 Список страниц", callback_data="ag:act:list_pages"))
    b.row(InlineKeyboardButton(text="📄 Текст main", callback_data="ag:act:page_main"))
    b.row(InlineKeyboardButton(text="📄 Текст help", callback_data="ag:act:page_help"))
    b.row(InlineKeyboardButton(text="📄 Другая страница…", callback_data="ag:ask:page_key"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_tariffs_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📋 Список тарифов", callback_data="ag:act:tariffs"))
    b.row(InlineKeyboardButton(text="🔎 Тариф по id…", callback_data="ag:ask:tariff_id"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_promo_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📋 Список промокодов", callback_data="ag:act:promos"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_panel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❤️ Healthcheck", callback_data="ag:act:panel_health"))
    b.row(InlineKeyboardButton(text="📥 List inbounds", callback_data="ag:act:inbounds"))
    b.row(InlineKeyboardButton(text="🔄 Preview sync", callback_data="ag:act:sync_preview"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_broadcast_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👁 Черновик рассылки", callback_data="ag:act:bc_draft"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()


def agent_code_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📁 bot/handlers", callback_data="ag:act:list_handlers"))
    b.row(InlineKeyboardButton(text="📁 bot/services", callback_data="ag:act:list_services"))
    b.row(InlineKeyboardButton(text="💬 Свободный запрос…", callback_data="ag:chat"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ag:home"))
    return b.as_markup()
