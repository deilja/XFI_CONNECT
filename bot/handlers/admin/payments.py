"""
Router of the “Payments” section.

Processes:
- Main payment screen
- Toggle for Stars/Crypto
- Setting up crypto payments
- Editing crypto settings
"""
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database.requests import (
    get_setting,
    set_setting,
    get_base_currency,
    get_currency_rate,
    set_currency_rate,
    is_crypto_enabled,
    is_stars_enabled,
    is_cards_enabled,
    is_yookassa_qr_enabled,
    is_demo_payment_enabled,
    is_wata_enabled,
    is_platega_enabled,
    is_cardlink_enabled,
)
from bot.states.admin_states import (
    AdminStates,
    CRYPTO_PARAMS,
    get_crypto_param_by_index,
    get_total_crypto_params
)
from bot.utils.admin import is_admin
from bot.utils.telegram_links import build_telegram_link
from bot.keyboards.admin import (
    payments_menu_kb,
    crypto_setup_kb,
    crypto_setup_confirm_kb,
    edit_crypto_kb,
    crypto_management_kb,
    cards_management_kb,
    qr_management_kb,
    wata_management_kb,
    platega_management_kb,
    cardlink_management_kb,
    payment_rates_kb,
    base_currency_switch_input_kb,
    base_currency_switch_confirm_kb,
    back_and_home_kb
)
from bot.utils.text import escape_html, safe_edit_or_send
from bot.services.base_currency import (
    BaseCurrencySwitchBlocked,
    build_base_currency_switch_preview,
    switch_base_currency,
)
from bot.services.money import format_money_minor

logger = logging.getLogger(__name__)

router = Router()
_RATE_MESSAGES: dict[int, Message] = {}


# ============================================================================
# AUXILIARY FUNCTIONS
# ============================================================================


def has_crypto_data() -> bool:
    """Checks whether crypto payment data is filled in the database."""
    url = get_setting('crypto_item_url', '')
    secret = get_setting('crypto_secret_key', '')
    return bool(url and secret)


def parse_item_id_from_url(url: str) -> str:
    """Extract the Ya.Seller item id from normal and test-mode start links."""
    try:
        value = (url or "").strip()
        if not value:
            return ""

        # ``item0-123`` must be checked before ``item-123``.  Otherwise the
        # generic branch can consume the prefix incorrectly.
        for marker in ("?start=item0-", "?start=item-"):
            if marker not in value:
                continue
            start_part = value.split(marker, 1)[1]
            item_id = start_part.split("-", 1)[0].split("&", 1)[0]
            return item_id if item_id.isdigit() else ""
    except (AttributeError, IndexError, TypeError):
        logger.warning("Не удалось разобрать Ya.Seller URL: %r", url)
    return ""


# ============================================================================
# MAIN PAYMENT SCREEN
# ============================================================================

@router.callback_query(F.data == "admin_payments")
async def show_payments_menu(callback: CallbackQuery, state: FSMContext):
    """Shows the main screen of the payment section."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    
    await state.set_state(AdminStates.payments_menu)

    stars = is_stars_enabled()
    crypto = is_crypto_enabled()
    cards = is_cards_enabled()
    qr = is_yookassa_qr_enabled()
    demo = is_demo_payment_enabled()
    wata = is_wata_enabled()
    platega = is_platega_enabled()
    cardlink = is_cardlink_enabled()

    text = (
        "💳 <b>Настройки оплаты</b>\n\n"
        "Здесь можно включить/выключить способы оплаты и настроить их.\n\n"
    )

    if stars:
        text += "🟢 <b>Telegram Stars</b>\n"
    else:
        text += "⚪ <b>Telegram Stars</b>\n"

    if crypto:
        item_url = get_setting('crypto_item_url', '')
        if item_url:
            text += f"🟢 <b>Крипто (@Ya_SellerBot)</b>\n<a href=\"{item_url}\">Ссылка на товар</a>\n"
        else:
            text += "🟢 <b>Крипто (@Ya_SellerBot)</b>\n"
    else:
        text += "⚪ <b>Крипто (@Ya_SellerBot)</b>\n"

    if cards:
        text += "🟢 <b>TG payments</b>\n"
    else:
        text += "⚪ <b>TG payments</b>\n"

    if qr:
        shop_id = get_setting('yookassa_shop_id', '')
        text += f"🟢 <b>ЮКасса</b> | Shop ID: <code>{shop_id or '—'}</code>\n"
    else:
        text += "⚪ <b>ЮКасса</b>\n"

    if wata:
        text += "🟢 <b>WATA</b>\n"
    else:
        text += "⚪ <b>WATA</b>\n"

    if platega:
        text += "🟢 <b>Platega</b>\n"
    else:
        text += "⚪ <b>Platega</b>\n"

    if cardlink:
        text += "🟢 <b>Cardlink</b>\n"
    else:
        text += "⚪ <b>Cardlink</b>\n"

    if demo:
        text += "🟢 <b>Демо оплата (РФ)</b>\n"
    else:
        text += "⚪ <b>Демо оплата (РФ)</b>\n"

    monthly_reset = get_setting('monthly_traffic_reset_enabled', '0') == '1'
    notify = get_setting('payment_notifications_enabled', '0') == '1'

    await safe_edit_or_send(callback.message,
        text,
        reply_markup=payments_menu_kb(stars, crypto, cards, qr, monthly_reset, demo, wata, platega, cardlink, notify_enabled=notify)
    )
    await callback.answer()


@router.callback_query(F.data == 'admin_payment_rates')
async def show_payment_rates(callback: CallbackQuery, state: FSMContext):
    """Shows the global base currency and fixed rates for new invoices."""
    if not is_admin(callback.from_user.id):
        await callback.answer('⛔ Доступ запрещён', show_alert=True)
        return
    await state.set_state(AdminStates.payments_menu)
    await _render_payment_rates(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith('admin_payment_rate_edit:'))
async def edit_payment_rate(callback: CallbackQuery, state: FSMContext):
    """Starts one Decimal rate edit while keeping the source message id."""
    if not is_admin(callback.from_user.id):
        await callback.answer('⛔ Доступ запрещён', show_alert=True)
        return
    target_currency = callback.data.split(':', 1)[1].upper()
    labels = {
        'RUB': 'RUB',
        'USD': 'USD',
        'USDT': 'USDT',
        'XTR': 'Stars',
    }
    base_currency = get_base_currency()
    if target_currency not in labels or target_currency == base_currency:
        await callback.answer('⚠️ Неизвестный курс', show_alert=True)
        return
    _RATE_MESSAGES[callback.from_user.id] = callback.message
    await state.set_state(AdminStates.payment_rate_value)
    await state.update_data(
        payment_rate_currency=target_currency,
        payment_rate_message_id=callback.message.message_id,
        payment_rate_chat_id=callback.message.chat.id,
    )
    await safe_edit_or_send(
        callback.message,
        (
            f"💱 <b>Курс {labels[target_currency]}</b>\n\n"
            f"Введите, сколько {labels[target_currency]} приходится на 1 {base_currency}.\n"
            "Можно использовать точку или запятую.\n\n"
            "Например: <code>1,05</code>"
        ),
        reply_markup=back_and_home_kb('admin_payment_rates'),
    )
    await callback.answer()


@router.message(AdminStates.payment_rate_value, F.text)
async def payment_rate_value_input(message: Message, state: FSMContext):
    """Stores a positive decimal string and redraws the original admin message."""
    from bot.utils.text import get_message_text_for_storage

    raw = get_message_text_for_storage(message, 'plain').strip().replace(',', '.')
    normalized = _normalize_positive_decimal(raw)
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    target_currency = data.get('payment_rate_currency')
    source_message = _RATE_MESSAGES.get(message.from_user.id)
    if not target_currency or normalized is None:
        await safe_edit_or_send(
            source_message or message,
            (
                "⚠️ <b>Некорректный курс</b>\n\n"
                "Введите положительное число, например <code>1,05</code>."
            ),
            reply_markup=back_and_home_kb('admin_payment_rates'),
            force_new=source_message is None,
        )
        return
    set_currency_rate(str(target_currency), normalized)
    await state.set_state(AdminStates.payments_menu)
    _RATE_MESSAGES.pop(message.from_user.id, None)
    await _render_payment_rates(source_message or message, force_new=source_message is None)


async def _render_payment_rates(message: Message, *, force_new: bool = False) -> None:
    base = get_base_currency()
    rows = [f"💵 Базовая валюта: <code>{base}</code>", ""]
    for target, icon, label in (
        ('RUB', '₽', 'RUB'),
        ('USD', '💵', 'USD'),
        ('USDT', '🪙', 'USDT'),
        ('XTR', '⭐', 'Stars'),
    ):
        if target == base:
            continue
        rate = get_currency_rate(target, base_currency=base)
        rendered = (
            escape_html(_format_rate_for_display(rate)) if rate else 'не настроен'
        )
        rows.append(f"{icon} 1 {base} = <code>{rendered} {label}</code>")
    await safe_edit_or_send(
        message,
        "💱 <b>Валюта и курсы</b>\n\n"
        + "\n".join(rows)
        + "\n\nНовый курс применяется только к новым счетам. Уже созданные счета не меняются.",
        reply_markup=payment_rates_kb(base),
        force_new=force_new,
    )


@router.callback_query(F.data.startswith('admin_base_currency_select:'))
async def select_base_currency(callback: CallbackQuery, state: FSMContext):
    """Starts the protected base-currency conversion wizard."""
    if not is_admin(callback.from_user.id):
        await callback.answer('⛔ Доступ запрещён', show_alert=True)
        return
    target = callback.data.split(':', 1)[1].upper()
    source = get_base_currency()
    if target not in {'RUB', 'USD'} or target == source:
        await callback.answer('⚠️ Некорректная валюта', show_alert=True)
        return
    _RATE_MESSAGES[callback.from_user.id] = callback.message
    await state.set_state(AdminStates.base_currency_transition_rate)
    await state.update_data(
        base_currency_from=source,
        base_currency_to=target,
    )
    await safe_edit_or_send(
        callback.message,
        (
            f"💵 <b>Переход {source} → {target}</b>\n\n"
            f"Введите, сколько {source} стоит 1 {target}.\n"
            f"Пример: <code>1 {target} = 90 {source}</code> — введите <code>90</code>.\n\n"
            "Перед применением бот покажет точный предварительный расчёт."
        ),
        reply_markup=base_currency_switch_input_kb(),
    )
    await callback.answer()


@router.message(AdminStates.base_currency_transition_rate, F.text)
async def base_currency_transition_rate_input(message: Message, state: FSMContext):
    """Builds and displays a non-mutating switch preview."""
    from bot.utils.text import get_message_text_for_storage

    raw = get_message_text_for_storage(message, 'plain').strip().replace(',', '.')
    data = await state.get_data()
    source = str(data.get('base_currency_from') or '')
    target = str(data.get('base_currency_to') or '')
    prompt = _RATE_MESSAGES.get(message.from_user.id)
    try:
        preview = build_base_currency_switch_preview(target, raw)
    except (TypeError, ValueError) as error:
        try:
            await message.delete()
        except Exception:
            pass
        await safe_edit_or_send(
            prompt or message,
            "⚠️ <b>Некорректный переходный курс</b>\n\n"
            "Введите положительное число не более 1 000 000.",
            reply_markup=base_currency_switch_input_kb(),
            force_new=prompt is None,
        )
        return
    try:
        await message.delete()
    except Exception:
        pass

    tariff_lines = []
    for tariff in preview.get('tariffs', [])[:12]:
        tariff_lines.append(
            f"• {escape_html(tariff['name'])}: "
            f"{format_money_minor(tariff['before_minor'], source)} → "
            f"{format_money_minor(tariff['after_minor'], target)}"
        )
    if len(preview.get('tariffs', [])) > 12:
        tariff_lines.append(f"• …ещё {len(preview['tariffs']) - 12}")
    blocking = int(preview.get('blocking_intents') or 0)
    warning = (
        f"\n\n❌ В обработке платежей: <b>{blocking}</b>. Сначала дождитесь их завершения."
        if blocking
        else ''
    )
    text = (
        f"💵 <b>Предварительный расчёт {source} → {target}</b>\n\n"
        f"Курс: <code>1 {target} = {escape_html(preview['old_units_per_new'])} {source}</code>\n\n"
        + ("\n".join(tariff_lines) or "Тарифов нет")
        + "\n\n"
        f"👥 Балансы: {format_money_minor(preview['balance_before_minor'], source)} → "
        f"{format_money_minor(preview['balance_after_minor'], target)}\n"
        f"🎁 Реферальные накопления: {format_money_minor(preview['referral_before_minor'], source)} → "
        f"{format_money_minor(preview['referral_after_minor'], target)}\n"
        f"🧾 Неоплаченных счетов будет отменено: <b>{preview['cancelable_intents']}</b>"
        f"{warning}\n\n"
        "Перед переключением будет создана проверенная резервная копия БД."
    )
    await state.set_state(AdminStates.base_currency_switch_confirm)
    await state.update_data(base_currency_transition_rate=preview['old_units_per_new'])
    await safe_edit_or_send(
        prompt or message,
        text,
        reply_markup=(
            base_currency_switch_input_kb()
            if blocking
            else base_currency_switch_confirm_kb()
        ),
        force_new=prompt is None,
    )
