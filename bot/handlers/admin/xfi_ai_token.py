"""Admin command for configuring the XFI AI Gateway token."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.xfi_ai_service import save_gateway_token, verify_gateway_token
from bot.utils.admin import is_admin

router = Router()


@router.message(Command("ai_token"))
async def set_ai_token(message: Message) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip().startswith("xfi_"):
        await message.answer(
            "Использование:\n/ai_token XFI_AI_TOKEN\n\n"
            "Токен выдаётся ботом XFI AI командой /token."
        )
        return

    token = parts[1].strip()
    if len(token) < 20 or len(token) > 512 or any(ch.isspace() for ch in token):
        await message.answer("Некорректный XFI AI токен.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    if not await verify_gateway_token(token):
        await message.answer(
            "XFI AI токен не прошёл проверку Gateway.\n"
            "Проверьте токен и доступность XFI AI."
        )
        return

    save_gateway_token(token)
    await message.answer(
        "XFI AI токен проверен и сохранён.\n"
        "Новые запросы /ai будут использовать этот токен."
    )
