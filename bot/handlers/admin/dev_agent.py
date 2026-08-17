"""DevAgent + кнопки Local YaAdmin."""
from __future__ import annotations

import json
import logging
import re

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.utils.admin import is_admin
from bot.utils.text import safe_edit_or_send
from bot.services.code_agent import CodeAgent
from bot.keyboards.agent_kb import (
    agent_home_kb,
    agent_stats_kb,
    agent_servers_kb,
    agent_keys_kb,
    agent_users_kb,
    agent_pages_kb,
    agent_tariffs_kb,
    agent_promo_kb,
    agent_panel_kb,
    agent_broadcast_kb,
    agent_code_kb,
    agent_back_kb,
)

logger = logging.getLogger(__name__)
router = Router(name="dev_agent")
_agents: dict[int, CodeAgent] = {}


class DevAgentStates(StatesGroup):
    chatting = State()
    waiting_input = State()


def _agent(admin_id: int) -> CodeAgent:
    if admin_id not in _agents:
        _agents[admin_id] = CodeAgent()
    return _agents[admin_id]


INTRO = (
    "🛠 <b>Local YaAdmin / DevAgent</b>\n\n"
    "Жми кнопки или пиши свободный текст.\n"
    "Свободный чат — кнопка «💬 Свободный чат»."
)


async def _run_tool(name: str, args: dict | None = None) -> str:
    args = args or {}
    agent = CodeAgent()  # для _run_tool без истории
    try:
        return await agent._run_tool(name, args)
    except Exception as e:
        logger.exception("quick tool %s", name)
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def _fmt(result: str) -> str:
    try:
        data = json.loads(result)
        return json.dumps(data, ensure_ascii=False, indent=2)[:4000]
    except Exception:
        return (result or "")[:4000]


# --- fixed actions: tool_name, args ---
ACTIONS = {
    "keys_stats": ("get_keys_stats", {}),
    "users_stats": ("get_users_stats", {}),
    "expiring_3": ("get_expiring_keys", {"days": 3}),
    "expiring_7": ("get_expiring_keys", {"days": 7}),
    "servers": ("get_servers_status", {}),
    "panel_health": ("check_panel_health", {}),
    "list_pages": ("list_pages", {}),
    "page_main": ("get_page", {"page_key": "main"}),
    "page_help": ("get_page", {"page_key": "help"}),
    "tariffs": ("list_tariffs", {}),
    "promos": ("list_promo_codes", {}),
    "inbounds": ("list_inbounds", {}),
    "sync_preview": ("preview_panel_sync", {}),
    "bc_draft": ("get_broadcast_draft", {}),
    "logs": ("read_bot_logs", {"lines": 40}),
}

# ask modes: prompt text + how to build tool call from user message
ASK = {
    "key_id": ("Введи key_id (число):", "get_key", lambda t: {"key_id": int(t.strip())}),
    "user_keys": ("Введи telegram_id:", "list_user_keys", lambda t: {"telegram_id": int(t.strip())}),
    "extend_key": (
        "Формат: <key_id> <дней>\nПример: 12 30",
        "extend_key",
        lambda t: {"key_id": int(t.split()[0]), "days": int(t.split()[1])},
    ),
    "user_id": ("Введи telegram_id:", "search_user", lambda t: {"telegram_id": int(t.strip())}),
    "username": ("Введи @username:", "search_user", lambda t: {"username": t.strip().lstrip("@")}),
    "balance": ("Введи telegram_id для баланса:", "get_user_balance", lambda t: {"telegram_id": int(t.strip())}),
    "payments": (
        "Введи telegram_id для статистики оплат:",
        "get_user_payments_stats",
        lambda t: {"telegram_id": int(t.strip())},
    ),
    "page_key": ("Введи page_key (например main):", "get_page", lambda t: {"page_key": t.strip()}),
    "tariff_id": ("Введи tariff_id:", "get_tariff", lambda t: {"tariff_id": int(t.strip())}),
}


@router.callback_query(F.data == "admin_code_agent")
async def start_agent(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔", show_alert=True)
    await callback.answer()
    _agent(callback.from_user.id)
    await state.set_state(DevAgentStates.chatting)
    await safe_edit_or_send(callback.message, INTRO, reply_markup=agent_home_kb())


@router.callback_query(F.data == "ag:home")
async def ag_home(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(DevAgentStates.chatting)
    await callback.answer()
    await safe_edit_or_send(callback.message, INTRO, reply_markup=agent_home_kb())


@router.callback_query(F.data == "ag:chat")
async def ag_chat_mode(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(DevAgentStates.chatting)
    await callback.answer()
    await callback.message.answer(
        "💬 Пиши задачу текстом (Groq).\nВыход из чата — кнопка «В меню агента».",
        reply_markup=agent_back_kb(),
    )


CAT_MAP = {
    "ag:cat:stats": ("📊 Статистика", agent_stats_kb),
    "ag:cat:servers": ("🖥️ Серверы", agent_servers_kb),
    "ag:cat:keys": ("🔑 Ключи", agent_keys_kb),
    "ag:cat:users": ("👥 Пользователи", agent_users_kb),
    "ag:cat:pages": ("📄 Страницы", agent_pages_kb),
    "ag:cat:tariffs": ("💳 Тарифы", agent_tariffs_kb),
    "ag:cat:promo": ("🎟 Промо", agent_promo_kb),
    "ag:cat:panel": ("📡 Панель 3X-UI", agent_panel_kb),
    "ag:cat:broadcast": ("📢 Рассылка", agent_broadcast_kb),
    "ag:cat:code": ("🛠 Код", agent_code_kb),
}


@router.callback_query(F.data.startswith("ag:cat:"))
async def ag_category(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    title, kb_fn = CAT_MAP.get(callback.data, (None, None))
    if not title:
        return
    await safe_edit_or_send(callback.message, f"<b>{title}</b>", reply_markup=kb_fn())


@router.callback_query(F.data.startswith("ag:act:"))
async def ag_action(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    key = callback.data.split(":", 2)[-1]

    # code list dirs via agent tools
    if key == "list_handlers":
        res = await _run_tool("list_files", {"rel_dir": "bot/handlers"})
        await callback.message.answer(f"<b>bot/handlers</b>\n<pre>{_fmt(res)}</pre>", parse_mode="HTML", reply_markup=agent_back_kb())
        return
    if key == "list_services":
        res = await _run_tool("list_files", {"rel_dir": "bot/services"})
        await callback.message.answer(f"<b>bot/services</b>\n<pre>{_fmt(res)}</pre>", parse_mode="HTML", reply_markup=agent_back_kb())
        return

    if key not in ACTIONS:
        await callback.message.answer("Неизвестное действие", reply_markup=agent_back_kb())
        return

    tool, args = ACTIONS[key]
    wait = await callback.message.answer("⏳ …")
    res = await _run_tool(tool, args)
    try:
        await wait.delete()
    except Exception:
        pass
    await callback.message.answer(
        f"<b>{key}</b>\n<pre>{_fmt(res)}</pre>",
        parse_mode="HTML",
        reply_markup=agent_back_kb(),
    )


@router.callback_query(F.data.startswith("ag:ask:"))
async def ag_ask(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    mode = callback.data.split(":")[-1]
    if mode not in ASK:
        return await callback.answer("?", show_alert=True)
    prompt, _, _ = ASK[mode]
    await state.set_state(DevAgentStates.waiting_input)
    await state.update_data(ask_mode=mode)
    await callback.answer()
    await callback.message.answer(prompt, reply_markup=agent_back_kb())


@router.message(DevAgentStates.waiting_input)
async def ag_input(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or not message.text:
        return
    data = await state.get_data()
    mode = data.get("ask_mode")
    if not mode or mode not in ASK:
        await state.set_state(DevAgentStates.chatting)
        return
    _, tool, builder = ASK[mode]
    try:
        args = builder(message.text)
    except Exception:
        await message.answer("Неверный формат. Попробуй ещё раз.", reply_markup=agent_back_kb())
        return
    await state.set_state(DevAgentStates.chatting)
    wait = await message.answer("⏳ …")
    res = await _run_tool(tool, args)
    try:
        await wait.delete()
    except Exception:
        pass
    await message.answer(f"<pre>{_fmt(res)}</pre>", parse_mode="HTML", reply_markup=agent_back_kb())


# report / rollback / reset / exit — как раньше
@router.callback_query(F.data == "code:report")
async def cb_report(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.answer(_agent(callback.from_user.id).report(), parse_mode="HTML", reply_markup=agent_home_kb())
    await callback.answer()


@router.callback_query(F.data == "code:rollback")
async def cb_rollback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.answer(_agent(callback.from_user.id).rollback(), reply_markup=agent_home_kb())
    await callback.answer()


@router.callback_query(F.data == "code:reset")
async def cb_reset(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    _agent(callback.from_user.id).reset_dialog()
    await state.set_state(DevAgentStates.chatting)
    await callback.message.answer("Новый чат.", reply_markup=agent_home_kb())
    await callback.answer()


@router.callback_query(F.data == "code:exit")
async def cb_exit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer()
    try:
        from bot.handlers.admin.main import show_admin_panel
        await show_admin_panel(callback, state)
    except Exception:
        await callback.message.answer("Выход.")


@router.message(DevAgentStates.chatting)
async def on_chat(message: Message, state: FSMContext):
    """Свободный текст → Groq."""
    if not is_admin(message.from_user.id) or not message.text:
        return
    if message.text.strip().lower() in {"выход", "exit", "/admin", "меню"}:
        await state.clear()
        await message.answer("Вышел. /code или админка.", reply_markup=agent_home_kb())
        return

    agent = _agent(message.from_user.id)
    wait = await message.answer("⏳ Groq…")
    try:
        result = await agent.chat(message.text)
    except Exception as e:
        logger.exception("chat")
        result = f"❌ {e}"
    try:
        await wait.delete()
    except Exception:
        pass
    await message.answer(result[:4000], reply_markup=agent_home_kb())
