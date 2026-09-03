"""Client for the XFI AI Gateway."""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

XFI_AI_BASE_URL = os.getenv("XFI_AI_BASE_URL", "http://127.0.0.1:8091").rstrip("/")
XFI_AI_API_KEY = os.getenv("XFI_AI_API_KEY", "").strip()
XFI_AI_MODEL = os.getenv("XFI_AI_MODEL", "").strip()
XFI_AI_TIMEOUT = float(os.getenv("XFI_AI_TIMEOUT", "45"))

SYSTEM_PROMPT = """
Ты — ИИ-ассистент технической поддержки VPN-сервиса XFI Connect.
Помогай с WireGuard, AmneziaWG, VLESS/Reality, Xray, 3X-UI, Happ, Hiddify,
v2RayTun, Amnezia, Incy и другими клиентами VPN.
Отвечай на русском языке, кратко, точно и пошагово. Не выдумывай настройки,
ключи, ссылки или результаты диагностики. Если данных недостаточно — попроси
только необходимые данные.
""".strip()


class XFI AIError(RuntimeError):
    """Gateway request failed or returned an invalid response."""


async def ask_xfi_ai(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """Send a chat request through the XFI AI Gateway."""
    if not XFI_AI_API_KEY:
        raise XFI AIError("XFI_AI_API_KEY is not configured")
    if not user_prompt or len(user_prompt) > 12000:
        raise XFI AIError("Prompt is empty or too large")

    body = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 1200,
    }
    if XFI_AI_MODEL:
        body["model"] = XFI_AI_MODEL

    headers = {"Authorization": f"Bearer {XFI_AI_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=XFI_AI_TIMEOUT) as client:
            response = await client.post(
                f"{XFI_AI_BASE_URL}/v1/chat/completions",
                json=body,
                headers=headers,
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("XFI AI Gateway request failed: %s", exc)
        raise XFI AIError("XFI AI Gateway request failed") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("XFI AI Gateway returned unexpected response")
        raise XFI AIError("Invalid XFI AI Gateway response") from exc

    if not isinstance(content, str) or not content.strip():
        raise XFI AIError("Empty XFI AI response")
    return content.strip()
