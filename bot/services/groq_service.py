import logging
from groq import AsyncGroq

# Импорт API-ключа из config.py
try:
    from config import GROQ_API_KEY
except ImportError:
    GROQ_API_KEY = None

logger = logging.getLogger(__name__)

# Инициализация асинхронного клиента Groq
client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """
Ты — вежливый ИИ-ассистент технической поддержки VPN-сервиса XFi Connect.
Твоя задача — помогать пользователям решать проблемы с подключением (WireGuard, VLESS, ShadowSocks, Outline), 
настройкой клиентов (v2rayNG, Happ, Streisand, Nekobox, Shadowrocket) и отвечать на их вопросы.
Отвечай кратко, понятным языком, без лишней воды.
"""

async def ask_groq(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """
    Отправляет запрос к модели llama-3.3-70b-versatile через Groq API.
    """
    if not client or not GROQ_API_KEY:
        logger.error("GROQ_API_KEY не задан в config.py")
        return "⚠️ Модуль ИИ временно недоступен (не настроен API-ключ в config.py)."

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при запросе к Groq API: {e}")
        return "⚠️ Произошла ошибка при обработке запроса ИИ-ассистентом."
