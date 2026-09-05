import contextlib
import logging
import os

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

from bot.utils.action_dispatcher import (
    CoreActionRequest,
    dispatch_core_action,
    register_core_action_executor,
)

logger = logging.getLogger(__name__)

router = Router()


def _trial_webapp_url() -> str:
    return os.getenv('TRIAL_VPN_WEBAPP_URL', '').strip()


def _trial_webapp_markup() -> InlineKeyboardMarkup | None:
    url = _trial_webapp_url()
    if not url or not url.startswith(('https://', 'http://')):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text='🌐 Получить тест на сайте',
                    web_app=WebAppInfo(url=url),
                )
            ],
            [
                InlineKeyboardButton(
                    text='🎁 Получить тест в боте',
                    callback_data='trial_activate',
                )
            ],
        ]
    )


@router.callback_query(F.data == 'trial_subscription')
async def show_trial_subscription(callback: CallbackQuery):
    """Shows the trial subscription page."""
    from bot.utils.page_renderer import render_page
    from database.requests import get_trial_tariff_id, has_used_trial, is_trial_enabled

    user_id = callback.from_user.id

    if not is_trial_enabled():
        await render_page(callback, page_key='action_unavailable')
        await callback.answer()
        return
    if get_trial_tariff_id() is None:
        logger.warning('Trial is enabled without a configured tariff')
        await render_page(callback, page_key='action_unavailable')
        await callback.answer()
        return
    if has_used_trial(user_id):
        await render_page(callback, page_key='trial_already_used')
        await callback.answer()
        return

    await render_page(callback, page_key='trial')
    markup = _trial_webapp_markup()
    if markup and callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=markup)
        except Exception as exc:
            logger.warning('Не удалось добавить Trial WebApp кнопку: %s', exc)
    await callback.answer()


@router.callback_query(F.data == 'trial_activate')
async def activate_trial_subscription(callback: CallbackQuery, state: FSMContext):
    """Activates a trial subscription: creates a key through a standard mechanism."""
    await dispatch_core_action(
        callback,
        'trial.activate',
        source='callback',
        state=state,
    )


async def _execute_trial_activate(request: CoreActionRequest) -> None:
    """Run the original trial activation after action policy resolution."""
    from bot.handlers.user.payments.keys_config import start_new_key_config
    from database.requests import (
        complete_order,
        create_initial_vpn_key,
        create_pending_order,
        get_or_create_user,
        get_tariff_by_id,
        get_trial_tariff_id,
        has_used_trial,
        is_trial_enabled,
        mark_trial_used,
    )

    target = request.target
    state = request.state
    user_id = request.telegram_id
    if state is None:
        await _render_trial_page(target, 'action_unavailable')
        return

    if not is_trial_enabled():
        await _render_trial_page(target, 'action_unavailable')
        return
    tariff_id = get_trial_tariff_id()
    if tariff_id is None:
        logger.warning('Trial is enabled without a configured tariff')
        await _render_trial_page(target, 'action_unavailable')
        return
    if has_used_trial(user_id):
        await _render_trial_page(target, 'trial_already_used')
        return

    tariff = get_tariff_by_id(tariff_id)
    if not tariff:
        logger.warning('Configured trial tariff %s was not found', tariff_id)
        await _render_trial_page(target, 'action_unavailable')
        return

    (user, _) = get_or_create_user(
        user_id,
        target.from_user.username,
        first_name=getattr(target.from_user, 'first_name', None),
        last_name=getattr(target.from_user, 'last_name', None),
    )
    internal_user_id = user['id']
    mark_trial_used(internal_user_id)
    logger.info(f'Пользователь {user_id} активировал пробный период (тариф ID={tariff_id})')

    duration_days = tariff['duration_days']
    traffic_limit_bytes = (tariff.get('traffic_limit_gb', 0) or 0) * 1024**3
    key_id = create_initial_vpn_key(
        internal_user_id,
        tariff_id,
        duration_days,
        traffic_limit=traffic_limit_bytes,
    )
    (_, order_id) = create_pending_order(
        user_id=internal_user_id,
        tariff_id=tariff_id,
        payment_type='trial',
        vpn_key_id=key_id,
    )
    complete_order(order_id)
    try:
        from bot.services.key_lifecycle import emit_key_lifecycle_event_safe

        await emit_key_lifecycle_event_safe(
            'key_created',
            {
                'key_id': key_id,
                'user_id': internal_user_id,
                'tariff_id': tariff_id,
                'days': duration_days,
                'traffic_limit': traffic_limit_bytes,
                'order_id': order_id,
                'payment_type': 'trial',
                'source': 'trial',
            },
        )
    except Exception as hook_err:
        logger.warning(f"Не удалось вызвать lifecycle hooks trial-ключа {key_id}: {hook_err}")

    try:
        from bot.services.notifications import notify_admins_payment
        from database.requests import find_order_by_order_id

        trial_order = find_order_by_order_id(order_id)
        if trial_order:
            await notify_admins_payment(target.bot, trial_order)
    except Exception as notify_err:
        logger.warning(f'Ошибка уведомления о trial: {notify_err}')

    await state.update_data(
        new_key_order_id=order_id,
        new_key_id=key_id,
        new_key_owner_telegram_id=user_id,
        new_key_owner_username=target.from_user.username,
    )
    target_message = target.message if isinstance(target, CallbackQuery) else target
    if isinstance(target, CallbackQuery):
        await target.answer()
        with contextlib.suppress(Exception):
            await target.message.delete()
    await start_new_key_config(
        target_message,
        state,
        order_id,
        key_id,
        owner_telegram_id=user_id,
        owner_username=target.from_user.username,
    )


async def _render_trial_page(target, page_key: str) -> None:
    """Render one database-backed trial state for callbacks and command redirects."""
    from bot.utils.page_renderer import render_page

    await render_page(
        target,
        page_key=page_key,
        force_new=not isinstance(target, CallbackQuery),
    )
    if isinstance(target, CallbackQuery):
        await target.answer()


register_core_action_executor('trial.activate', _execute_trial_activate, replace=True)
