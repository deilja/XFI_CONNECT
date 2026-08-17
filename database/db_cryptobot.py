"""Persistent settings for the built-in Crypto Pay adapter."""
from __future__ import annotations

from typing import Optional

from .connection import get_db

CRYPTOBOT_ENABLED_SETTING = "cryptobot_enabled"
CRYPTOBOT_TOKEN_SETTING = "cryptobot_api_token"


def is_cryptobot_enabled() -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (CRYPTOBOT_ENABLED_SETTING,),
        ).fetchone()
    return bool(row and str(row["value"] or "") == "1")


def get_cryptobot_token() -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (CRYPTOBOT_TOKEN_SETTING,),
        ).fetchone()
    return str(row["value"] or "").strip() if row else ""


def set_cryptobot_token(token: str) -> None:
    value = str(token or "").strip()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (CRYPTOBOT_TOKEN_SETTING, value),
        )


def set_cryptobot_enabled(enabled: bool) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (CRYPTOBOT_ENABLED_SETTING, "1" if enabled else "0"),
        )


def is_cryptobot_configured() -> bool:
    return is_cryptobot_enabled() and bool(get_cryptobot_token())


__all__ = [
    "get_cryptobot_token",
    "is_cryptobot_configured",
    "is_cryptobot_enabled",
    "set_cryptobot_enabled",
    "set_cryptobot_token",
]
