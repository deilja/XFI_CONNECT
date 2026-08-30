"""Plain-language admin entry point for the unified AI stack."""
from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from bot.services.ai_key_store import AIKeyStore
from bot.services.ai_model_selector import AIModelSelector
from bot.services.ai_task_router import AITaskRouter
from bot.services.ai_key_monitor import AIKeyHealthMonitor

try:
    from config import ADMIN_IDS
except ImportError:
    ADMIN_IDS = set()

router = Router()


def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return False
    if isinstance(ADMIN_IDS, (set, list, tuple, dict)):
        return user_id in ADMIN_IDS or str(user_id) in ADMIN_IDS or any(str(x).isdigit() and int(x) == user_id for x in ADMIN_IDS)
    try:
        return int(ADMIN_IDS) == user_id
    except Exception:
        return False


def _monitor(bot: types.Bot) -> AIKeyHealthMonitor | None:
    loop = getattr(bot, "ai_key_monitor_loop", None)
    return getattr(loop, "monitor", None) if loop else None


@router.message(Command("ai"))
async def cmd_ai(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: /ai <задача>\n\nПример: /ai проверь ошибку в оплате")
        return
    await _handle(message, parts[1])


@router.message()
async def plain_admin_ai(message: types.Message):
    if not message.text or message.text.startswith("/") or not is_admin(message.from_user.id):
        return
    await _handle(message, message.text)


async def _handle(message: types.Message, text: str):
    monitor = _monitor(message.bot)
    if monitor is None:
        await message.reply("AI Supervisor ещё не инициализирован.")
        return
    available = monitor.available()
    if not available:
        await message.reply("❌ Нет доступных AI-провайдеров. Проверьте /ai_keys.")
        return

    class Inventory:
        def available(self):
            return {provider: monitor.state[provider].models for provider in monitor.available()}

    routed = AITaskRouter(AIModelSelector(Inventory())).route(text)
    if routed.choice is None:
        await message.reply("❌ Не удалось выбрать рабочую AI-модель.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    from bot.services.ai_agent import AIAgent
    agent = AIAgent(provider=routed.choice.provider, key_store=AIKeyStore("data/ai_keys.enc"))
    answer = await agent.chat(text, role=f"admin task: {routed.task_type}")
    await message.reply(f"AI: {routed.choice.provider}/{routed.choice.model}\n\n{answer}")
