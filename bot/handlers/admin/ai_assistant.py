"""AI-ассистент админ-панели XFI CONNECT."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from config import ADMIN_IDS
from bot.services.ai_agent import AIAgent
from bot.services.ai_autopilot import AIAutopilot
from bot.services.ai_autopilot_policy import is_cancel, is_confirmation

logger = logging.getLogger(__name__)
router = Router(name="ai_assistant")
_agents: dict[int, AIAgent] = {}
_autopilots: dict[int, AIAutopilot] = {}


class AIStates(StatesGroup):
    chatting = State()
    awaiting_confirmation = State()


def _get_agent(admin_id: int) -> AIAgent:
    if admin_id not in _agents:
        _agents[admin_id] = AIAgent(provider=getattr(config, "AI_DEFAULT_PROVIDER", "groq"))
    return _agents[admin_id]


def _get_autopilot(admin_id: int) -> AIAutopilot:
    if admin_id not in _autopilots:
        _autopilots[admin_id] = AIAutopilot(_get_agent(admin_id))
    return _autopilots[admin_id]


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _ai_keyboard(provider: str) -> InlineKeyboardMarkup:
    mark_groq = "✅ " if provider == "groq" else ""
    mark_grok = "✅ " if provider == "grok" else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{mark_groq}Groq", callback_data="ai:provider:groq"), InlineKeyboardButton(text=f"{mark_grok}Grok", callback_data="ai:provider:grok")],
        [InlineKeyboardButton(text="🗑 Новый чат", callback_data="ai:reset"), InlineKeyboardButton(text="◀️ Назад", callback_data="ai:exit")],
    ])


def _plan_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнить", callback_data=f"ai:execute:{token}"), InlineKeyboardButton(text="❌ Отмена", callback_data=f"ai:cancel:{token}")]
    ])


def _format_plan(plan) -> str:
    lines = [
        "🤖 <b>План AI Supervisor</b>",
        f"\n<b>Задача:</b> {plan.request}",
        f"<b>Риск:</b> {plan.risk}",
        f"<b>Что будет сделано:</b> {plan.summary}",
    ]
    if plan.steps:
        lines.append("<b>Шаги:</b>\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(plan.steps, 1)))
    if plan.verification:
        lines.append("<b>Проверка:</b>\n" + "\n".join(f"• {x}" for x in plan.verification))
    if plan.rollback:
        lines.append("<b>Откат:</b>\n" + "\n".join(f"• {x}" for x in plan.rollback))
    lines.append("\nИзменения не выполнялись. Для запуска требуется явное подтверждение администратора.")
    return "\n".join(lines)[:3900]


@router.message(Command("ai", "groq", "grok"))
async def cmd_ai(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    agent = _get_agent(message.from_user.id)
    await state.set_state(AIStates.chatting)
    await message.answer("🤖 <b>AI Supervisor</b>\n\nПишите задачу обычным текстом. Для изменений агент сначала сформирует план, затем запросит подтверждение.\n\nПримеры:\n• «проверь весь проект»\n• «найди и исправь ошибку оплаты»\n• «усиль безопасность»", reply_markup=_ai_keyboard(agent.provider), parse_mode="HTML")


@router.callback_query(F.data.in_({"ai:open", "admin_ai_assistant", "admin_ai"}))
async def cb_ai_open(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    agent = _get_agent(callback.from_user.id)
    await state.set_state(AIStates.chatting)
    await callback.message.edit_text("🤖 <b>AI Supervisor</b>\n\nПишите задачу обычным текстом. Изменения выполняются только после подтверждения.", reply_markup=_ai_keyboard(agent.provider), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.in_({"ai:exit", "admin:main"}))
async def cb_ai_exit(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.answer("Вышли из AI-ассистента")


@router.callback_query(F.data.startswith("ai:provider:"))
async def cb_provider(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    provider = callback.data.split(":", 2)[-1]
    if provider not in {"groq", "grok"}:
        await callback.answer("Неподдерживаемый AI-провайдер", show_alert=True)
        return
    agent = _get_agent(callback.from_user.id)
    try:
        agent.set_provider(provider)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.set_state(AIStates.chatting)
    await callback.message.edit_text(f"🤖 <b>AI Supervisor</b>\n\nПровайдер: <b>{provider.upper()}</b>\nИстория чата очищена.", reply_markup=_ai_keyboard(provider), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "ai:reset")
async def cb_reset(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _get_agent(callback.from_user.id).reset()
    _get_autopilot(callback.from_user.id).pending.clear()
    await state.set_state(AIStates.chatting)
    await callback.message.edit_text("🤖 <b>AI Supervisor</b>\n\nЧат и ожидающие планы очищены.", reply_markup=_ai_keyboard(_get_agent(callback.from_user.id).provider), parse_mode="HTML")
    await callback.answer("Очищено")


@router.callback_query(F.data.startswith("ai:cancel:"))
async def cb_plan_cancel(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    token = callback.data.split(":", 2)[-1]
    cancelled = _get_autopilot(callback.from_user.id).cancel(token)
    await state.set_state(AIStates.chatting)
    await callback.message.edit_text("❌ План отменён." if cancelled else "❌ План уже недоступен.", reply_markup=_ai_keyboard(_get_agent(callback.from_user.id).provider))
    await callback.answer()


@router.callback_query(F.data.startswith("ai:execute:"))
async def cb_plan_execute(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    token = callback.data.split(":", 2)[-1]
    autopilot = _get_autopilot(callback.from_user.id)
    try:
        plan = autopilot.authorize(token)
    except KeyError:
        await callback.answer("План истёк или уже выполнен", show_alert=True)
        return
    # Deliberately no arbitrary shell executor here. The application must register
    # a narrow, audited executor that delegates updates to xfi_update/health services.
    await state.set_state(AIStates.chatting)
    await callback.message.edit_text(
        "⚠️ План подтверждён, но исполнитель изменений ещё не подключён.\n\n"
        "Это fail-closed поведение: AI не получает произвольный shell/Git доступ.\n"
        f"Задача: {plan.summary}\n\n"
        "Подключите зарегистрированный application executor для фактического выполнения.",
        reply_markup=_ai_keyboard(_get_agent(callback.from_user.id).provider),
    )
    await callback.answer("Подтверждено, выполнение остановлено безопасно")


@router.message(AIStates.chatting)
async def process_ai_message(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id) or not message.text:
        return
    text = message.text.strip()
    if text.lower() in {"/start", "/admin", "назад", "выход", "exit"}:
        await state.clear()
        await message.answer("Вышел из AI-ассистента.")
        return
    autopilot = _get_autopilot(message.from_user.id)
    if is_confirmation(text):
        await message.answer("Подтверждение действует только через кнопку конкретного плана.")
        return
    if is_cancel(text):
        await message.answer("Отменять план нужно кнопкой «Отмена».")
        return
    wait_msg = await message.answer("⏳ Анализирую задачу и проверяю контекст проекта...")
    try:
        token, plan = await autopilot.prepare(text)
        await wait_msg.delete()
        await message.answer(_format_plan(plan), reply_markup=_plan_keyboard(token), parse_mode="HTML")
        await state.set_state(AIStates.awaiting_confirmation)
    except Exception:
        logger.exception("AI autopilot planning error")
        await wait_msg.edit_text("❌ Не удалось подготовить безопасный план. Подробности записаны в журнал.")


@router.message(AIStates.awaiting_confirmation)
async def process_waiting_plan(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("Ожидается подтверждение конкретного плана кнопкой «Выполнить» или «Отмена».")
