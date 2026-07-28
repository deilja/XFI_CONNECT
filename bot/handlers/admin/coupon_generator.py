"""Administrator wizard for generating batches of one-time coupons."""

from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.admin import promotion_cancel_kb
from bot.states.admin_states import AdminStates
from bot.utils.admin import is_admin
from bot.utils.text import get_message_text_for_storage, safe_edit_or_send
from database.requests import create_coupon_batch

router = Router()


async def _delete_input(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "admin_coupons_generate")
async def admin_coupons_generate(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await state.set_state(AdminStates.coupon_generate_discount)
    await safe_edit_or_send(
        callback.message,
        "🎲 <b>Генератор купонов</b>\n\n"
        "Введите размер скидки от 0 до 100%.",
        reply_markup=promotion_cancel_kb("admin_coupons"),
    )
    await callback.answer()


@router.message(
    AdminStates.coupon_generate_discount,
    F.text,
    ~F.text.startswith("/"),
)
async def admin_coupons_generate_discount(
    message: Message,
    state: FSMContext,
):
    if not is_admin(message.from_user.id):
        return
    raw = get_message_text_for_storage(message, "plain").strip()
    await _delete_input(message)
    if not raw.isdigit() or not 0 <= int(raw) <= 100:
        await safe_edit_or_send(
            message,
            "❌ Введите число от 0 до 100.",
            reply_markup=promotion_cancel_kb("admin_coupons"),
            force_new=True,
        )
        return
    await state.update_data(coupon_generate_discount=int(raw))
    await state.set_state(AdminStates.coupon_generate_lifetime)
    await safe_edit_or_send(
        message,
        "⏳ <b>Срок жизни</b>\n\nВведите количество дней.",
        reply_markup=promotion_cancel_kb("admin_coupons"),
        force_new=True,
    )


@router.message(
    AdminStates.coupon_generate_lifetime,
    F.text,
    ~F.text.startswith("/"),
)
async def admin_coupons_generate_lifetime(
    message: Message,
    state: FSMContext,
):
    if not is_admin(message.from_user.id):
        return
    raw = get_message_text_for_storage(message, "plain").strip()
    await _delete_input(message)
    if not raw.isdigit() or int(raw) <= 0:
        await safe_edit_or_send(
            message,
            "❌ Введите количество дней больше 0.",
            reply_markup=promotion_cancel_kb("admin_coupons"),
            force_new=True,
        )
        return
    await state.update_data(coupon_generate_lifetime=int(raw))
    await state.set_state(AdminStates.coupon_generate_count)
    await safe_edit_or_send(
        message,
        "🔢 <b>Количество</b>\n\n"
        "Введите количество купонов. За один раз можно создать до 500.",
        reply_markup=promotion_cancel_kb("admin_coupons"),
        force_new=True,
    )


@router.message(
    AdminStates.coupon_generate_count,
    F.text,
    ~F.text.startswith("/"),
)
async def admin_coupons_generate_count(
    message: Message,
    state: FSMContext,
):
    if not is_admin(message.from_user.id):
        return
    raw = get_message_text_for_storage(message, "plain").strip()
    await _delete_input(message)
    if not raw.isdigit() or not 1 <= int(raw) <= 500:
        await safe_edit_or_send(
            message,
            "❌ Введите число от 1 до 500.",
            reply_markup=promotion_cancel_kb("admin_coupons"),
            force_new=True,
        )
        return
    data = await state.get_data()
    coupons = create_coupon_batch(
        discount_percent=data["coupon_generate_discount"],
        lifetime_days=data["coupon_generate_lifetime"],
        count=int(raw),
        source="admin_generated",
        created_by_admin_id=message.from_user.id,
    )
    await state.clear()
    codes = "\n".join(coupon["code"] for coupon in coupons)
    text = (
        "✅ <b>Купоны сгенерированы</b>\n\n"
        f"Скидка: <b>{data['coupon_generate_discount']}%</b>\n"
        f"Срок жизни: <b>{data['coupon_generate_lifetime']} дн.</b>\n"
        f"Количество: <b>{len(coupons)}</b>\n\n"
        f"<pre>{html.escape(codes)}</pre>"
    )
    await safe_edit_or_send(
        message,
        text,
        reply_markup=promotion_cancel_kb("admin_coupons"),
        force_new=True,
    )
