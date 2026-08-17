import os
import re
import uuid
import shutil
import logging
import py_compile
from pathlib import Path

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.groq_service import ask_groq

try:
    from config import ADMIN_IDS
except ImportError:
    ADMIN_IDS = set()

logger = logging.getLogger(__name__)
router = Router()

BASE_DIR = Path("/root/XFI_CONNECT").resolve()

PENDING_TASKS = {}

DEV_SYSTEM_PROMPT = """
Ты — Senior Python Developer и архитектор VPN-бота XFI_CONNECT (aiogram 3, asyncio, Linux, systemd).

Помогай писать качественный Python-код, проектировать архитектуру, создавать SQL-запросы, миграции БД и команды Linux.

Если возвращаешь код Python — обязательно возвращай полный рабочий файл.
"""

EDIT_SYSTEM_PROMPT = """
Ты — инструмент безопасного редактирования Python-файлов.

Тебе будет передан полный исходный код файла и инструкция пользователя.

Правила:

1. Верни полный изменённый файл.
2. Не сокращай код.
3. Не используй комментарии вроде:
   '# остальной код без изменений'
4. Ответ должен содержать только Python-код.
5. Не добавляй пояснений.
"""


def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return False

    if isinstance(ADMIN_IDS, (set, list, tuple, dict)):
        return (
            user_id in ADMIN_IDS
            or str(user_id) in ADMIN_IDS
            or any(
                str(x).isdigit() and int(x) == user_id
                for x in ADMIN_IDS
            )
        )

    try:
        return int(ADMIN_IDS) == user_id
    except Exception:
        return False


def extract_code_block(text: str) -> str:
    match = re.search(
        r"```(?:python)?\s*(.*?)```",
        text,
        re.DOTALL,
    )

    if match:
        return match.group(1).strip()

    return text.strip()


def _safe_project_path(path: Path) -> bool:
    """Ensure a pending edit still points inside the project tree."""
    try:
        resolved = path.resolve()
        return resolved == BASE_DIR or BASE_DIR in resolved.parents
    except (OSError, RuntimeError):
        return False


@router.message(Command("dev"))
async def cmd_dev(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.reply(
            "👨‍💻 Dev Assistant\n\n"
            "Использование:\n"
            "/dev <вопрос>\n\n"
            "Например:\n"
            "/dev Как оптимизировать этот SQL?"
        )
        return

    await message.bot.send_chat_action(
        chat_id=message.chat.id,
        action="typing",
    )

    try:
        answer = await ask_groq(
            args[1],
            system_prompt=DEV_SYSTEM_PROMPT,
        )

        await message.reply(answer)

    except Exception as e:
        logger.exception("Ошибка Dev Assistant")

        await message.reply(
            f"❌ Ошибка при обращении к ИИ:\n{e}"
        )


@router.message(Command("dev_edit"))
async def cmd_dev_edit(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=2)

    if len(args) < 3:
        await message.reply(
            "Использование:\n"
            "/dev_edit <путь_к_файлу> <инструкция>\n\n"
            "Пример:\n"
            "/dev_edit bot/services/groq_service.py "
            "Добавь логирование времени ответа"
        )
        return

    rel_path = args[1].lstrip("/")
    instruction = args[2]

    target_path = (BASE_DIR / rel_path).resolve()

    if not _safe_project_path(target_path):
        await message.reply(
            "⛔ Запрещён выход за пределы проекта."
        )
        return

    if not target_path.exists():
        await message.reply(
            f"❌ Файл не найден:\n{rel_path}"
        )
        return

    try:
        current_code = target_path.read_text(
            encoding="utf-8"
        )
    except Exception as e:
        await message.reply(
            f"❌ Ошибка чтения файла:\n{e}"
        )
        return

    await message.reply(
        f"⏳ Анализирую файл:\n{rel_path}"
    )

    await message.bot.send_chat_action(
        chat_id=message.chat.id,
        action="typing",
    )

    prompt = (
        f"Файл: {rel_path}\n\n"
        f"{current_code}\n\n"
        f"Измени согласно инструкции:\n"
        f"{instruction}"
    )

    try:
        response = await ask_groq(
            prompt,
            system_prompt=EDIT_SYSTEM_PROMPT,
        )
    except Exception as e:
        await message.reply(
            f"❌ Groq вернул ошибку:\n{e}"
        )
        return

    new_code = extract_code_block(response)

    if not new_code:
        await message.reply(
            "❌ ИИ не вернул код."
        )
        return

    if new_code.strip() == current_code.strip():
        await message.reply(
            "⚠️ Изменений не найдено."
        )
        return

    task_id = uuid.uuid4().hex[:8]

    PENDING_TASKS[task_id] = {
        "path": target_path,
        "rel_path": rel_path,
        "old_code": current_code,
        "new_code": new_code,
    }

    preview = (
        new_code[:1500] + "\n..."
        if len(new_code) > 1500
        else new_code
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Применить",
                    callback_data=f"apply_code:{task_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"cancel_code:{task_id}",
                ),
            ]
        ]
    )

    await message.reply(
        "📝 Предпросмотр:\n\n"
        f"{preview}",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("cancel_code:"))
async def cb_cancel_code(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    task_id = callback.data.split(":", 1)[1]

    PENDING_TASKS.pop(task_id, None)

    await callback.message.edit_text(
        "❌ Применение изменений отменено."
    )

    await callback.answer()


@router.callback_query(F.data.startswith("apply_code:"))
async def cb_apply_code(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    task_id = callback.data.split(":", 1)[1]

    task = PENDING_TASKS.pop(task_id, None)

    if task is None:
        await callback.message.edit_text(
            "⚠️ Время действия задачи истекло."
        )
        await callback.answer()
        return

    target_path = Path(task["path"])
    rel_path = task["rel_path"]
    new_code = task["new_code"]

    if not _safe_project_path(target_path):
        logger.error("Rejected unsafe pending edit path: %s", target_path)
        await callback.message.edit_text(
            "⛔ Путь задачи больше не находится внутри проекта."
        )
        await callback.answer()
        return

    backup_path = target_path.with_suffix(
        target_path.suffix + ".bak"
    )

    try:
        shutil.copy2(target_path, backup_path)

        target_path.write_text(
            new_code,
            encoding="utf-8",
        )

        py_compile.compile(
            str(target_path),
            doraise=True,
        )

    except py_compile.PyCompileError as e:
        if backup_path.exists():
            shutil.copy2(
                backup_path,
                target_path,
            )

        logger.exception(
            "Ошибка синтаксиса в %s",
            rel_path,
        )

        await callback.message.edit_text(
            "❌ Синтаксическая ошибка.\n\n"
            "Файл автоматически восстановлен.\n\n"
            f"{e}"
        )

        await callback.answer()
        return

    except Exception as e:
        if backup_path.exists():
            shutil.copy2(
                backup_path,
                target_path,
            )

        logger.exception(
            "Ошибка применения патча"
        )

        await callback.message.edit_text(
            f"❌ Ошибка:\n{e}\n\n"
            "Файл восстановлен."
        )

        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Перезапустить xfi-connect",
                    callback_data="restart_service",
                )
            ]
        ]
    )

    await callback.message.edit_text(
        "✅ Изменения успешно применены.\n\n"
        f"📄 {rel_path}\n"
        f"💾 Создан резервный файл:\n"
        f"{backup_path.name}\n\n"
        "Проверка синтаксиса пройдена.",
        reply_markup=keyboard,
    )

    await callback.answer()


@router.callback_query(F.data == "restart_service")
async def cb_restart_service(
    callback: types.CallbackQuery,
):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "🔄 Выполняется перезапуск службы..."
    )

    code = os.system(
        "systemctl restart xfi-connect"
    )

    if code == 0:
        await callback.message.edit_text(
            "✅ Служба xfi-connect успешно перезапущена."
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось перезапустить службу.\n"
            "Проверьте журнал:\n"
            "journalctl -u xfi-connect -n 50"
        )

    await callback.answer()
