"""Resolve XFI CONNECT Telegram administrator IDs without XFI Guard coupling."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_ai_admin_ids() -> list[int]:
    """Return configured XFI CONNECT admin IDs; never read XFI Guard settings."""
    raw = os.getenv("XFI_CONNECT_ADMIN_IDS") or os.getenv("ADMIN_IDS", "")
    ids: list[int] = []
    for value in raw.replace(";", ",").split(","):
        value = value.strip()
        if not value:
            continue
        try:
            admin_id = int(value)
        except ValueError:
            logger.warning("Некорректный Telegram admin id в XFI CONNECT configuration")
            continue
        if admin_id > 0:
            ids.append(admin_id)
    return list(dict.fromkeys(ids))
