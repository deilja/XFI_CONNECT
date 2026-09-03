"""Telegram handler for the XFI AI Gateway."""

import logging

from aiogram import Router, types
from aiogram.filters import Command

from bot.services.xfi_ai_service import XFIAIError, ask_xfi_ai

router = Router()
logger = logging.getLogger(__name__)
MAX_TELEGRAM_MESSAGE = 4096


def _split_message(text: str, limit: int = MAX_TELEGRAM_MESSAGE) -> list[str]:
    """Split long AI responses without losing content."""
    if len(text) <= limit:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < 1:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks


@router.message(Command("ai"))
async def cmd_ai(message: types.Message):
    """Answer a user question through the XFI AI Gateway."""
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.reply(
            "Задайте вопрос ИИ-ассистенту.\n\n"
            "Пример:\n/ai Как настроить VLESS Reality на iPhone?"
        )
        return

    user_query = args[1].strip()
    if not user_query:
        await message.reply("Вопрос не должен быть пустым.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        answer = await ask_xfi_ai(user_query)
    except XFIAIError:
        logger.exception("XFI AI Gateway error for Telegram user %s", message.from_user.id if message.from_user else "unknown")
        await message.reply(
            "ИИ-ассистент временно недоступен. Попробуйте повторить запрос позже."
        )
        return

    for chunk in _split_message(answer):
        await message.reply(chunk)
