import logging
import httpx
from openai import AsyncOpenAI
import config

logger = logging.getLogger(__name__)

class AIAgent:
    def __init__(self, provider: str = "openrouter"):
        self.provider = provider
        self.history = []
        
        # OpenRouter API
        or_key = getattr(config, "GROQ_API_KEY", "")
        self.or_client = AsyncOpenAI(
            api_key=or_key, 
            base_url="https://api.groq.com/openai/v1"
        ) if or_key else None

        # Grok (xAI API)
        grok_key = getattr(config, "GROK_API_KEY", getattr(config, "XAI_API_KEY", ""))
        self.grok_client = AsyncOpenAI(
            api_key=grok_key, 
            base_url="https://api.x.ai/v1"
        ) if grok_key else None

    def set_provider(self, provider: str):
        self.provider = provider
        self.reset()

    def reset(self):
        self.history.clear()

    async def _get_active_free_models(self) -> list[str]:
        """Динамически запрашивает актуальный список всех БЕСПЛАТНЫХ моделей OpenRouter."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                res = await http_client.get("https://api.groq.com/openai/v1/models")
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    # Фильтруем только те, что заканчиваются на :free
                    free_models = [m["id"] for m in data if m.get("id", "").endswith(":free")]
                    if free_models:
                        return free_models
        except Exception as e:
            logger.warning(f"Не удалось динамически получить модели: {e}")

        # Резервный список на случай сбоя API каталога
        return [
            "llama-3.3-70b-versatile",
            "llama-3.3-70b-versatile",
            "llama-3.3-70b-versatile"
        ]

    async def chat(self, prompt: str) -> str:
        if self.provider == "grok":
            return await self._call_grok(prompt)
        else:
            return await self._call_openrouter(prompt)

    async def _call_openrouter(self, prompt: str) -> str:
        if not self.or_client:
            return "❌ Ошибка: GROQ_API_KEY не указан в config.py"
        
        # Запрашиваем только свежие и активные бесплатные модели
        active_models = await self._get_active_free_models()
        last_error = ""

        for model_name in active_models:
            try:
                response = await self.or_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "Ты полезный и умный ИИ-ассистент администратора VPN-сервиса."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"Модель {model_name} временно не ответила: {e}")
                last_error = str(e)
                continue

        return f"❌ Все бесплатные модели OpenRouter временно недоступны. Ошибка: {last_error}"

    async def _call_grok(self, prompt: str) -> str:
        if not self.grok_client:
            return "❌ Ошибка: GROK_API_KEY не прописан в config.py"
        try:
            response = await self.grok_client.chat.completions.create(
                model="grok-beta",
                messages=[
                    {"role": "system", "content": "Ты полезный и умный ИИ-ассистент администратора VPN-сервиса."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.exception("Grok error")
            return f"❌ Ошибка Grok: {e}"
