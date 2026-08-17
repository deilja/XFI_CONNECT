from aiogram import Router, types
from aiogram.filters import Command
from bot.services.groq_service import ask_groq

router = Router()

@router.message(Command("ai"))
async def cmd_ai(message: types.Message):
    # Извлекаем текст вопроса после команды /ai
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply(
            "🤖 **Задайте вопрос ИИ-ассистенту.**\n\n"
            "Пример:\n`/ai Как настроить VLESS на iPhone?`",
            parse_mode="Markdown"
        )
        return

    user_query = args[1]
    
    # Отправляем плашку "печатает..."
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    # Запрос к Groq
    answer = await ask_groq(user_query)
    
    await message.reply(answer, parse_mode="Markdown")
