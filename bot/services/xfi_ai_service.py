"""Client for the XFI AI Gateway."""

import logging
import os
from pathlib import Path

import httpx

import config

logger = logging.getLogger(__name__)

try:
    XFI_AI_TIMEOUT = float(os.getenv("XFI_AI_TIMEOUT", "45"))
except ValueError:
    XFI_AI_TIMEOUT = 45.0
XFI_AI_TIMEOUT = min(max(XFI_AI_TIMEOUT, 5.0), 120.0)

XFI_AI_TOKEN_FILE = Path(
    os.getenv("XFI_AI_TOKEN_FILE")
    or os.getenv("XFI_AI_KEY_FILE")
    or getattr(config, "XFI_AI_KEY_FILE", "data/xfi_ai_api_key")
)

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


def _base_url() -> str:
    # Environment variables must override config.py defaults so deployments and tests
    # can redirect the gateway without modifying the generated config.py file.
    configured = os.getenv("XFI_AI_BASE_URL", "").strip()
    if not configured:
        configured = str(getattr(config, "XFI_AI_BASE_URL", "")).strip()
    return configured.rstrip("/")


def _token_file() -> Path:
    return Path(XFI_AI_TOKEN_FILE)


def get_gateway_token() -> str:
    """Read the integration credential from the bootstrap-managed protected file."""
    try:
        token = _token_file().read_text(encoding="utf-8").strip()
    except OSError:
        token = os.getenv("XFI_AI_API_KEY", "").strip()
    return token if token.startswith("xfi_") and len(token) <= 512 else ""


def save_gateway_token(token: str) -> None:
    """Atomically store the gateway credential with owner-only permissions."""
    token = token.strip()
    if not token or not token.startswith("xfi_") or len(token) > 512:
        raise XFIAIError("Invalid XFI AI Gateway token")
    path = _token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(f"{token}\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


async def verify_gateway_token(token: str) -> bool:
    """Verify an integration credential without exposing its value in logs."""
    token = token.strip()
    base_url = _base_url()
    if not token or not base_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=XFI_AI_TIMEOUT) as client:
            response = await client.get(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {token}"},
            )
        return response.status_code == 200
    except httpx.HTTPError as exc:
        logger.warning("XFI AI Gateway token verification failed: %s", type(exc).__name__)
        return False


async def ask_xfi_ai(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """Send a chat request through the XFI AI Gateway."""
    token = get_gateway_token()
    base_url = _base_url()
    if not token:
        raise XFIAIError("XFI AI Gateway token is not configured")
    if not base_url:
        raise XFIAIError("XFI AI Gateway URL is not configured")
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
    model = os.getenv("XFI_AI_MODEL", "").strip()
    if model:
        body["model"] = model

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=XFI_AI_TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/v1/chat/completions",
                json=body,
                headers=headers,
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("XFI AI Gateway request failed: %s", type(exc).__name__)
        raise XFIAIError("XFI AI Gateway request failed") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("XFI AI Gateway returned unexpected response")
        raise XFIAIError("Invalid XFI AI Gateway response") from exc

    if not isinstance(content, str) or not content.strip():
        raise XFIAIError("Empty XFI AI response")
    return content.strip()
