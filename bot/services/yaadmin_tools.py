"""Local YaAdmin tools (ops + ui pages)."""
from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


YAADMIN_TOOLS = [
    {"type": "function", "function": {"name": "get_servers_status", "description": "Список VPN-серверов 3X-UI", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "toggle_server", "description": "Вкл/выкл сервер", "parameters": {"type": "object", "properties": {"server_id": {"type": "integer"}}, "required": ["server_id"]}}},
    {"type": "function", "function": {"name": "get_keys_stats", "description": "Статистика ключей", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_users_stats", "description": "Статистика пользователей", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_expiring_keys", "description": "Ключи, истекающие через N дней", "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "search_user", "description": "Поиск пользователя", "parameters": {"type": "object", "properties": {"telegram_id": {"type": "integer"}, "username": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_user_keys", "description": "Ключи пользователя", "parameters": {"type": "object", "properties": {"telegram_id": {"type": "integer"}}, "required": ["telegram_id"]}}},
    {"type": "function", "function": {"name": "get_key", "description": "Ключ по id или email", "parameters": {"type": "object", "properties": {"key_id": {"type": "integer"}, "panel_email": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "extend_key", "description": "Продлить ключ на N дней", "parameters": {"type": "object", "properties": {"key_id": {"type": "integer"}, "days": {"type": "integer"}}, "required": ["key_id", "days"]}}},
    {"type": "function", "function": {"name": "reset_key_traffic", "description": "Сброс notification трафика ключа", "parameters": {"type": "object", "properties": {"key_id": {"type": "integer"}}, "required": ["key_id"]}}},
    {"type": "function", "function": {"name": "delete_key", "description": "Удалить ключ", "parameters": {"type": "object", "properties": {"key_id": {"type": "integer"}}, "required": ["key_id"]}}},
    {"type": "function", "function": {"name": "toggle_user_ban", "description": "Бан/разбан", "parameters": {"type": "object", "properties": {"telegram_id": {"type": "integer"}}, "required": ["telegram_id"]}}},
    {"type": "function", "function": {"name": "get_user_balance", "description": "Баланс по telegram_id", "parameters": {"type": "object", "properties": {"telegram_id": {"type": "integer"}}, "required": ["telegram_id"]}}},
    {"type": "function", "function": {"name": "list_pages", "description": "Список page_key", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_page", "description": "Данные страницы", "parameters": {"type": "object", "properties": {"page_key": {"type": "string"}}, "required": ["page_key"]}}},
    {"type": "function", "function": {"name": "set_page_text", "description": "CUSTOM-текст страницы", "parameters": {"type": "object", "properties": {"page_key": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["page_key", "new_text"]}}},
    {"type": "function", "function": {"name": "get_setting", "description": "Настройка бота", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "set_setting", "description": "Записать настройку", "parameters": {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]}}},
    {"type": "function", "function": {"name": "read_bot_logs", "description": "Логи systemd xfi-connect", "parameters": {"type": "object", "properties": {"lines": {"type": "integer"}}}}},
]


async def execute_yaadmin_tool(name: str, args: dict) -> str:
    try:
        if name == "get_servers_status":
            from database.db_servers import get_all_servers
            out = []
            for s in get_all_servers():
                out.append({
                    "id": s.get("id"), "name": s.get("name"),
                    "panel_url": s.get("panel_url") or s.get("host"),
                    "is_active": bool(s.get("is_active")),
                    "panel_version": s.get("panel_version"),
                })
            return _ok(out)

        if name == "toggle_server":
            from database.db_servers import toggle_server_active
            sid = int(args["server_id"])
            st = toggle_server_active(sid)
            return _err(f"Сервер {sid} не найден") if st is None else _ok({"server_id": sid, "is_active": bool(st)})

        if name == "get_keys_stats":
            from database.db_stats import get_keys_stats
            return _ok(get_keys_stats())

        if name == "get_users_stats":
            from database.db_users import get_users_stats
            return _ok(get_users_stats())

        if name == "get_expiring_keys":
            from database.db_stats import get_expiring_keys
            return _ok(get_expiring_keys(int(args.get("days") or 3)))

        if name == "search_user":
            from database.db_users import get_user_by_telegram_id, get_user_by_username
            if args.get("telegram_id"):
                u = get_user_by_telegram_id(int(args["telegram_id"]))
                return _ok(u) if u else _err("Не найден")
            if args.get("username"):
                u = get_user_by_username(str(args["username"]).lstrip("@"))
                return _ok(u) if u else _err("Не найден")
            return _err("Нужен telegram_id или username")

        if name == "list_user_keys":
            from database.db_keys import get_user_keys_for_display
            return _ok(get_user_keys_for_display(int(args["telegram_id"])))

        if name == "get_key":
            from database.db_keys import get_vpn_key_by_id, get_user_by_panel_email
            if args.get("key_id"):
                k = get_vpn_key_by_id(int(args["key_id"]))
                return _ok(k) if k else _err("Не найден")
            if args.get("panel_email"):
                u = get_user_by_panel_email(args["panel_email"])
                return _ok(u) if u else _err("Не найден")
            return _err("Нужен key_id или panel_email")

        if name == "extend_key":
            from database.db_keys import extend_vpn_key
            kid, days = int(args["key_id"]), int(args["days"])
            return _ok({"key_id": kid, "days": days, "extended": bool(extend_vpn_key(kid, days))})

        if name == "reset_key_traffic":
            from database.db_keys import reset_key_traffic_notification
            reset_key_traffic_notification(int(args["key_id"]))
            return _ok({"key_id": int(args["key_id"]), "reset": True})

        if name == "delete_key":
            from database.db_keys import delete_vpn_key
            kid = int(args["key_id"])
            return _ok({"key_id": kid, "deleted": bool(delete_vpn_key(kid))})

        if name == "toggle_user_ban":
            from database.db_users import toggle_user_ban
            tid = int(args["telegram_id"])
            st = toggle_user_ban(tid)
            return _err("Не найден") if st is None else _ok({"telegram_id": tid, "banned": bool(st)})

        if name == "get_user_balance":
            from database.db_users import get_user_by_telegram_id, get_user_balance
            tid = int(args["telegram_id"])
            u = get_user_by_telegram_id(tid)
            if not u:
                return _err("Не найден")
            uid = int(u.get("id") or u.get("user_id"))
            return _ok({"telegram_id": tid, "user_id": uid, "balance_minor": get_user_balance(uid)})

        if name == "list_pages":
            from database.db_pages import get_page_keys
            return _ok(sorted(get_page_keys()))

        if name == "get_page":
            from database.db_pages import get_page
            p = get_page(args["page_key"])
            return _ok(p) if p else _err("Страница не найдена")

        if name == "set_page_text":
            from database.db_pages import update_page_custom
            update_page_custom(args["page_key"], text=args["new_text"])
            return _ok({"page_key": args["page_key"], "updated": True})

        if name == "get_setting":
            from database.db_settings import get_setting
            return _ok({"key": args["key"], "value": get_setting(args["key"])})

        if name == "set_setting":
            from database.db_settings import set_setting
            set_setting(args["key"], str(args["value"]))
            return _ok({"key": args["key"], "saved": True})

        if name == "read_bot_logs":
            n = max(5, min(int(args.get("lines") or 40), 120))
            res = subprocess.run(
                ["journalctl", "-u", "xfi-connect", "-n", str(n), "--no-pager"],
                capture_output=True, text=True, timeout=15,
            )
            return _ok({"logs": (res.stdout or res.stderr or "")[-8000:]})

        return _err(f"Неизвестный tool: {name}")
    except Exception as e:
        logger.exception("yaadmin %s", name)
        return _err(str(e))
