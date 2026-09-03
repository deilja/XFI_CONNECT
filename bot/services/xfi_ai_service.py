"""Client for the XFI AI Gateway."""

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

XFI_AI_BASE_URL = os.getenv("XFI_AI_BASE_URL", "http://127.0.0.1:8091").rstrip("/")
XFI_AI_MODEL = os.getenv("XFI_AI_MODEL", "").strip()
XFI_AI_TOKEN_FILE = Path(os.getenv("XFI_AI_TOKEN_FILE", "data/xfi_ai_gateway_token"))
try:
    XFI_AI_TIMEOUT = float(os.getenv("XFI_AI_TIMEOUT", "45"))
except ValueError:
    XFI_AI_TIMEOUT = 45.0
XFI_AI_TIMEOUT = min(max(XFI_AI_TIMEOUT, 5.0), 120.0)

SYSTEM_PROMPT = """
Ты — ИИ-ассистент технической поддержки VPN-сервиса XFI Connect.
Помогай с WireGuard, AmneziaWG, VLESS/Reality, Xray, 3X-UI, Happ, Hiddify,
v2RayTun, Amnezia, Incy и другими клиентами VPN.
Отвечай на русском языке, кратко, точно и пошагово. Не выдумывай настройки,
ключи, ссылки или результаты диагностики. Если данных недостаточно — попроси
только необходимые данные.
""".strip()


class XFIAIError(RuntimeError):
    """Gateway request failed or returned an invalid response."""


def get_gateway_token() -> str:
    """Read the Gateway token from the local protected file."""
    try:
        return XFI_AI_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return os.getenv("XFI_AI_API_KEY", "").strip()


async def verify_gateway_token(token: str) -> bool:
    """Verify a token against the Gateway without exposing its value in logs."""
    token = token.strip()
    if not token or not token.startswith("xfi_"):
        return False
    try:
        async with httpx.AsyncClient(timeout=XFI_AI_TIMEOUT) as client:
            response = await client.get(
                f"{XFI_AI_BASE_URL}/v1/models",
                headers={"Authorization": f"Bearer {token}"},
            )
        return response.status_code == 200
    except httpx.HTTPError as exc:
        logger.warning("XFI AI Gateway token verification failed: %s", exc)
        return False


def save_gateway_token(token: str) -> None:
    """Atomically save the Gateway token with owner-only permissions."""
    token = token.strip()
    if not token:
        raise ValueError("token is empty")
    XFI_AI_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = XFI_AI_TOKEN_FILE.with_name(f".{XFI_AI_TOKEN_FILE.name}.tmp")
    try:
        tmp_file.write_text(token + "\n", encoding="utf-8")
        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, XFI_AI_TOKEN_FILE)
        os.chmod(XFI_AI_TOKEN_FILE, 0o600)
    finally:
        try:
            tmp_file.unlink()
        except FileNotFoundError:
            pass


async def ask_xfi_ai(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """Send a chat request through the XFI AI Gateway."""
    token = get_gateway_token()
    if not token:
        raise XFIAIError("XFI AI Gateway token is not configured")
    if not user_prompt or len(user_prompt) > 12000:
        raise XFIAIError("Prompt is empty or too large")

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

    headers = {"Authorization": f"Bearer {token}"}
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
        raise XFIAIError("XFI AI Gateway request failed") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("XFI AI Gateway returned unexpected response")
        raise XFIAIError("Invalid XFI AI Gateway response") from exc

    if not isinstance(content, str) or not content.strip():
        raise XFIAIError("Empty XFI AI response")
    return content.strip()
