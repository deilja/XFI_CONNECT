from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx

import config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
KEY_FILE = Path(os.getenv("XFI_AI_KEY_FILE", "data/xfi_ai_api_key"))


def _read_key() -> str:
    try:
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return key if key.startswith("xfi_") and len(key) <= 512 else ""


def _save_key(key: str) -> None:
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key + "\n", encoding="utf-8")
    try:
        KEY_FILE.chmod(0o600)
    except OSError:
        pass


def _base_url() -> str:
    return str(getattr(config, "XFI_AI_BASE_URL", os.getenv("XFI_AI_BASE_URL", ""))).rstrip("/")


def _apply_key(key: str) -> None:
    # Keep the existing configuration contract; never log the credential.
    config.XFI_AI_API_KEY = key
    os.environ["XFI_AI_API_KEY"] = key


async def bootstrap_xfi_ai() -> bool:
    """Load an existing integration key or bootstrap one once using a server-side credential."""
    base_url = _base_url()
    if not base_url:
        logger.info("XFI AI bootstrap skipped: XFI_AI_BASE_URL is not configured")
        return False

    key = _read_key()
    timeout = httpx.Timeout(float(getattr(config, "XFI_AI_TIMEOUT", DEFAULT_TIMEOUT)))
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, follow_redirects=False) as client:
        if key:
            try:
                response = await client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
                if response.is_success:
                    _apply_key(key)
                    logger.info("XFI AI integration key verified")
                    return True
            except httpx.HTTPError as exc:
                logger.warning("XFI AI existing key health check failed: %s", type(exc).__name__)

        bootstrap = os.getenv("XFI_CONNECT_BOOTSTRAP_TOKEN", "").strip()
        if not bootstrap:
            logger.warning("XFI AI bootstrap unavailable: XFI_CONNECT_BOOTSTRAP_TOKEN is not configured")
            return False

        payload = {
            "integration_id": "xfi-connect",
            "name": "XFI CONNECT",
        }
        try:
            response = await client.post(
                "/v1/integrations/register",
                headers={"X-XFI-Registration-Token": bootstrap},
                json=payload,
            )
            if not response.is_success:
                logger.warning("XFI AI registration failed: HTTP %s", response.status_code)
                return False
            data = response.json()
            issued = str(data.get("api_key", ""))
            if not issued.startswith("xfi_") or len(issued) > 512:
                logger.warning("XFI AI registration returned an invalid credential")
                return False
            _save_key(issued)
            _apply_key(issued)
            logger.info("XFI AI integration registered and credential stored")
            return True
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("XFI AI registration error: %s", type(exc).__name__)
            return False
