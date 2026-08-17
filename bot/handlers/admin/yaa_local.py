"""Локальный /yaa без облака Yadreno."""
from __future__ import annotations
import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
from bot.services.code_agent import CodeAgent

logger = logging.getLogger(__name__)
router = Router(name="yaa_local")
_agents: dict[int, CodeAgent] = {}


@router.message(Command("yaa"))
async def cmd_yaa(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "🛠 <b>Локальный /yaa</b>\n"
            "Пример: <code>/yaa покажи текст страницы main</code>",
            parse_mode="HTML",
        )
        return
    task = parts[1].strip()
    data = await state.get_data()
    page_key = data.get("yaa_page_key") or data.get("current_page_key") or data.get("page_key")
    if page_key:
        task = f"Контекст page_key={page_key}. Задача: {task}"
    uid = message.from_user.id
    if uid not in _agents:
        _agents[uid] = CodeAgent()
    wait = await message.answer("🛠 …")
    try:
        result = await _agents[uid].chat(task)
    except Exception as e:
        logger.exception("yaa")
        result = f"❌ {e}"
    try:
        await wait.delete()
    except Exception:
        pass
    await message.answer(result[:4000])
