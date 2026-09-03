"""Admin command for configuring the XFI AI Gateway token."""

import os
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.utils.admin import is_admin

router = Router()
TOKEN_FILE = Path(os.getenv("XFI_AI_TOKEN_FILE", "data/xfi_ai_gateway_token"))


def _save_token(token: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)


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

    _save_token(token)
    await message.answer(
        "XFI AI токен сохранён в защищённом файле.\n"
        "Новые запросы /ai будут использовать этот токен."
    )
