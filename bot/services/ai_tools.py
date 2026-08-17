"""
Инструменты AI-агента для XFI_CONNECT.
Базовый набор: мониторинг, ключи, кастомизация страниц.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "get_servers_status",
            "description": "Список серверов 3X-UI и их статус",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_keys_stats",
            "description": "Общая статистика ключей (всего / активных / истекших)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_expiring_keys",
            "description": "Ключи, которые истекают в ближайшие N дней",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "За сколько дней до истечения (по умолчанию 3)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_key",
            "description": "Найти ключ по ID или panel_email",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_id": {"type": "integer"},
                    "panel_email": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_user_keys",
            "description": "Все ключи пользователя по telegram_id",
            "parameters": {
                "type": "object",
                "properties": {
                    "telegram_id": {"type": "integer"}
                },
                "required": ["telegram_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extend_key",
            "description": "Продлить ключ на указанное количество дней",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_id": {"type": "integer"},
                    "days": {"type": "integer"},
                },
                "required": ["key_id", "days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reset_key_traffic",
            "description": "Сбросить использованный трафик ключа",
            "parameters": {
                "type": "object",
                "properties": {"key_id": {"type": "integer"}},
                "required": ["key_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_key",
            "description": "Удалить ключ из базы",
            "parameters": {
                "type": "object",
                "properties": {"key_id": {"type": "integer"}},
                "required": ["key_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page",
            "description": "Получить данные страницы бота (текст, кнопки)",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_key": {
                        "type": "string",
                        "description": "Ключ страницы: main, help, trial, my_keys, referral и т.д.",
                    }
                },
                "required": ["page_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_page_text",
            "description": "Изменить текст страницы бота (кастомизация)",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_key": {"type": "string"},
                    "new_text": {
                        "type": "string",
                        "description": "Новый HTML-текст",
                    },
                },
                "required": ["page_key", "new_text"],
            },
        },
    },
]


async def execute_tool(name: str, args: dict) -> str:
    try:
        if name == "get_servers_status":
            from database.db_servers import get_all_servers

            servers = get_all_servers()
            result = []
            for s in servers:
                result.append({
                    "id": s["id"],
                    "name": s.get("name"),
                    "host": s.get("host"),
                    "active": bool(s.get("is_active")),
                    "panel_version": s.get("panel_version"),
                    "panel_api_profile": s.get("panel_api_profile"),
                })
            return _ok(result)

        elif name == "get_keys_stats":
            from database.db_stats import get_keys_stats
            return _ok(get_keys_stats())

        elif name == "get_expiring_keys":
            from database.db_stats import get_expiring_keys
            days = int(args.get("days") or 3)
            if days < 0:
                return _err("days не может быть отрицательным")
            return _ok(get_expiring_keys(days))

        elif name == "search_key":
            from database.db_keys import get_vpn_key_by_id, get_user_by_panel_email

            if args.get("key_id"):
                key = get_vpn_key_by_id(int(args["key_id"]))
                return _ok(key) if key else _err("Ключ не найден")
            if args.get("panel_email"):
                user = get_user_by_panel_email(args["panel_email"])
                return _ok(user) if user else _err("Пользователь по email не найден")
            return _err("Укажи key_id или panel_email")

        elif name == "list_user_keys":
            from database.db_keys import get_user_keys_for_display
            keys = get_user_keys_for_display(int(args["telegram_id"]))
            return _ok(keys)

        elif name == "extend_key":
            from bot.services.key_lifecycle import renew_key_access

            key_id = int(args["key_id"])
            days = int(args["days"])
            if days <= 0:
                return _err("Количество дней должно быть больше 0")
            if days > 3650:
                return _err("Нельзя продлить ключ более чем на 3650 дней за одну операцию")

            result = await renew_key_access(key_id, days)
            if not result.get("db_updated"):
                return _err("Не удалось продлить ключ")
            return _ok({"key_id": key_id, "days": days, **result})

        elif name == "reset_key_traffic":
            from database.db_keys import reset_key_traffic_notification

            key_id = int(args["key_id"])
            reset_key_traffic_notification(key_id)
            return _ok({"key_id": key_id, "reset": True})

        elif name == "delete_key":
            from database.db_keys import delete_vpn_key

            ok = delete_vpn_key(int(args["key_id"]))
            return _ok({"deleted": ok, "key_id": args["key_id"]})

        elif name == "get_page":
            from database.db_pages import get_page

            page = get_page(args["page_key"])
            return _ok(page) if page else _err(f"Страница {args['page_key']} не найдена")

        elif name == "set_page_text":
            from database.db_pages import update_page_custom

            update_page_custom(args["page_key"], text=args["new_text"])
            return _ok({"page_key": args["page_key"], "updated": True})

        else:
            return _err(f"Неизвестный tool: {name}")

    except Exception as e:
        logger.exception("Ошибка tool %s", name)
        return _err(str(e))
