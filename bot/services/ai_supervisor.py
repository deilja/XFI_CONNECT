"""Единый автономный AI Supervisor для XFI_CONNECT.

Агент принимает обычный русский текст от администратора через DevAgent,
а этот модуль периодически запускает тот же CodeAgent в режиме наблюдения.
Никаких отдельных специализированных агентов: один агент использует
существующий набор инструментов проекта и формирует единый отчёт.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any

from bot.services.code_agent import CodeAgent

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MIN = 30

_MONITOR_TASK: asyncio.Task | None = None
_MONITOR_BOT: Any | None = None
_LAST_DIGEST = ""

MONITOR_PROMPT = """Ты автономный AI Supervisor проекта XFI_CONNECT.
Проведи безопасный read-only мониторинг всего проекта и его runtime.

Проверь последовательно:
1. Архитектуру и структуру файлов проекта.
2. Python-код: синтаксис, Ruff, явные ошибки и подозрительные места.
3. Telegram/aiogram handlers, FSM, admin access и callbacks.
4. AI-контур: CodeAgent, AI context, модели, fallback и ошибки интеграции.
5. Базу/данные и очевидные проблемы совместимости.
6. 3X-UI/Xray/панель через доступные инструменты, только диагностика.
7. systemd-сервис xfi-connect, статус и последние ошибки journal.
8. Git/CI и незакоммиченные или опасные изменения, если доступны через локальные инструменты.
9. Производительность и потенциальные утечки ресурсов.
10. Безопасность: секреты, опасные операции, чрезмерные права, отсутствие проверок admin.
11. Что можно улучшить архитектурно, надёжности, безопасности, производительности и UX.

ВАЖНО:
- Ничего не изменяй.
- Не перезапускай сервисы.
- Не вызывай операции изменения панели, балансов, ключей, тарифов или страниц.
- Используй только чтение, диагностику и анализ.
- Если какой-то пункт невозможно проверить — явно укажи это.

Ответ строго в формате:
STATUS: OK или STATUS: ALERT

Затем:
КРИТИЧНО: ... (если нет — "нет")
ПРЕДУПРЕЖДЕНИЯ: ... (если нет — "нет")
УЛУЧШЕНИЯ: 3–7 конкретных предложений с приоритетом P1/P2/P3
ПРОВЕРЕНО: краткий перечень реально выполненных проверок

Не выдумывай результаты инструментов. Отделяй факт от рекомендации.
"""


def _interval_seconds() -> int:
    try:
        minutes = int(os.getenv("XFI_AI_MONITOR_INTERVAL_MIN", str(DEFAULT_INTERVAL_MIN)))
    except ValueError:
        minutes = DEFAULT_INTERVAL_MIN
    return max(5, minutes) * 60


def _digest(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8", errors="ignore")).hexdigest()


def monitor_status() -> dict[str, Any]:
    return {
        "running": bool(_MONITOR_TASK and not _MONITOR_TASK.done()),
        "interval_min": _interval_seconds() // 60,
        "last_digest": _LAST_DIGEST[:12] if _LAST_DIGEST else None,
    }


async def _monitor_loop(bot: Any, admin_ids: list[int]) -> None:
    global _LAST_DIGEST
    # Первый запуск выполняется сразу после включения мониторинга.
    while True:
        try:
            agent = CodeAgent()
            agent.new_session()
            report = await agent.chat(MONITOR_PROMPT)
            report = (report or "").strip()
            digest = _digest(report)

            # OK не отправляем каждый цикл. ALERT отправляем всегда при новом отчёте.
            is_alert = "STATUS: ALERT" in report.upper()
            changed = digest != _LAST_DIGEST
            if is_alert and changed:
                _LAST_DIGEST = digest
                text = "🤖 <b>XFI AI Supervisor — обнаружены изменения/проблемы</b>\n\n" + report
                for admin_id in admin_ids:
                    try:
                        await bot.send_message(admin_id, text[:4000], parse_mode="HTML")
                    except Exception:
                        logger.exception("failed to send AI monitor report to admin %s", admin_id)
            elif not _LAST_DIGEST:
                _LAST_DIGEST = digest

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AI supervisor monitor cycle failed")

        await asyncio.sleep(_interval_seconds())


def start_monitor(bot: Any, admin_ids: list[int]) -> asyncio.Task:
    """Запускает единственный фоновой монитор проекта."""
    global _MONITOR_TASK, _MONITOR_BOT
    _MONITOR_BOT = bot
    if _MONITOR_TASK and not _MONITOR_TASK.done():
        return _MONITOR_TASK
    _MONITOR_TASK = asyncio.create_task(_monitor_loop(bot, admin_ids), name="xfi-ai-supervisor")
    return _MONITOR_TASK


def stop_monitor() -> None:
    global _MONITOR_TASK
    if _MONITOR_TASK and not _MONITOR_TASK.done():
        _MONITOR_TASK.cancel()
    _MONITOR_TASK = None
