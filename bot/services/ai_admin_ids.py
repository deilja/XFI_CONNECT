"""Resolve Telegram administrator IDs without hardcoding them."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_ai_admin_ids() -> list[int]:
    raw = os.getenv("XFI_GUARD_ADMIN_IDS") or os.getenv("XFI_CONNECT_ADMIN_IDS") or os.getenv("ADMIN_IDS", "")
    ids: list[int] = []
    for value in raw.replace(";", ",").split(","):
        value = value.strip()
        if not value:
            continue
        try:
            ids.append(int(value))
        except ValueError:
            logger.warning("Некорректный Telegram admin id в переменной окружения")
    return list(dict.fromkeys(ids))
