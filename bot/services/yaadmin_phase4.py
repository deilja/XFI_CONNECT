"""
Фаза 4: баланс, hide/show кнопок, health панели (read-only), реф, оплаты юзера.
"""
from __future__ import annotations

import inspect
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


PHASE4_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "adjust_user_balance",
            "description": "Пополнить или списать баланс пользователя (через business operation если доступно)",
            "parameters": {
                "type": "object",
                "properties": {
                    "telegram_id": {"type": "integer"},
                    "amount_minor": {
                        "type": "integer",
                        "description": "Сумма в минорных единицах (копейки). + пополнение, - списание",
                    },
                    "reason": {"type": "string"},
                },
                "required": ["telegram_id", "amount_minor"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_page_button_hidden",
            "description": "Скрыть или показать кнопку на странице по label или id",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_key": {"type": "string"},
                    "button_label": {"type": "string"},
                    "button_id": {"type": "string"},
                    "is_hidden": {"type": "boolean"},
                },
                "required": ["page_key", "is_hidden"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_panel_health",
            "description": "Read-only проверка доступности серверов/панелей 3X-UI",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_id": {"type": "integer", "description": "Опционально один server_id"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_referral_coefficient",
            "description": "Индивидуальный реферальный коэффициент пользователя",
            "parameters": {
                "type": "object",
                "properties": {
                    "telegram_id": {"type": "integer"},
                    "coefficient": {"type": "number"},
                },
                "required": ["telegram_id", "coefficient"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_payments_stats",
            "description": "Статистика оплат пользователя",
            "parameters": {
                "type": "object",
                "properties": {"telegram_id": {"type": "integer"}},
                "required": ["telegram_id"],
            },
        },
    },
]


def _parse_buttons(page: dict) -> tuple[Any, str]:
    """Возвращает (buttons_obj, source_key)."""
    for key in ("buttons_custom", "buttons", "buttons_default"):
        val = page.get(key)
        if val in (None, ""):
            continue
        if isinstance(val, str):
            try:
                return json.loads(val), key
            except json.JSONDecodeError:
                continue
        return val, key
    return None, ""


def _walk_set_hidden(obj: Any, *, label: str | None, bid: str | None, hidden: bool) -> tuple[Any, int]:
    count = 0
    if isinstance(obj, list):
        out = []
        for item in obj:
            ni, c = _walk_set_hidden(item, label=label, bid=bid, hidden=hidden)
            out.append(ni)
            count += c
        return out, count
    if isinstance(obj, dict):
        d = dict(obj)
        match = False
        if bid and str(d.get("id") or "") == str(bid):
            match = True
        if label and str(d.get("label") or d.get("text") or "") == label:
            match = True
        if match:
            d["is_hidden"] = bool(hidden)
            count += 1
        for k, v in list(d.items()):
            if isinstance(v, (list, dict)):
                nv, c = _walk_set_hidden(v, label=label, bid=bid, hidden=hidden)
                d[k] = nv
                count += c
        return d, count
    return obj, 0


async def execute_phase4_tool(name: str, args: dict) -> str:
    try:
        if name == "adjust_user_balance":
            from database.db_users import get_user_by_telegram_id, get_user_balance

            tid = int(args["telegram_id"])
            amount = int(args["amount_minor"])
            reason = str(args.get("reason") or "local_yaadmin")
            u = get_user_by_telegram_id(tid)
            if not u:
                return _err("Пользователь не найден")
            uid = int(u.get("id") or u.get("user_id"))
            before = get_user_balance(uid)

            try:
                from database.db_business_operations import apply_balance_operation
                # типичная сигнатура может отличаться — пробуем несколько
                try:
                    apply_balance_operation(
                        user_id=uid,
                        amount_cents=amount,
                        reason=reason,
                        reference=f"yaadmin:{tid}",
                    )
                except TypeError:
                    apply_balance_operation(uid, amount, reason)
            except Exception:
                from database.db_users import add_to_balance, deduct_from_balance
                if amount >= 0:
                    ok = add_to_balance(uid, amount)
                else:
                    ok = deduct_from_balance(uid, abs(amount))
                if not ok:
                    return _err("Не удалось изменить баланс")

            after = get_user_balance(uid)
            return _ok({
                "telegram_id": tid,
                "user_id": uid,
                "before": before,
                "after": after,
                "delta": amount,
            })

        if name == "set_page_button_hidden":
            from database.db_pages import get_page, update_page_custom

            page_key = args["page_key"]
            hidden = bool(args["is_hidden"])
            label = args.get("button_label")
            bid = args.get("button_id")
            if not label and not bid:
                return _err("Нужен button_label или button_id")
            page = get_page(page_key)
            if not page:
                return _err("Страница не найдена")
            buttons, source = _parse_buttons(page)
            if buttons is None:
                return _err("Нет buttons JSON")
            new_b, n = _walk_set_hidden(buttons, label=label, bid=bid, hidden=hidden)
            if n == 0:
                return _err("Кнопка не найдена")
            if "buttons" not in inspect.signature(update_page_custom).parameters:
                return _err("update_page_custom без buttons")
            update_page_custom(page_key, buttons=json.dumps(new_b, ensure_ascii=False))
            return _ok({"page_key": page_key, "updated_buttons": n, "is_hidden": hidden, "source": source})

        if name == "check_panel_health":
            from database.db_servers import get_all_servers, get_server_by_id

            sid = args.get("server_id")
            servers = [get_server_by_id(int(sid))] if sid else get_all_servers()
            servers = [s for s in servers if s]
            results = []
            for s in servers:
                item = {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "is_active": bool(s.get("is_active")),
                    "panel_version": s.get("panel_version"),
                    "reachable": None,
                    "error": None,
                }
                try:
                    from bot.services.panels.xui import XUIClient
                    client = XUIClient(s)
                    # мягкая проверка метаданных / версии
                    if hasattr(client, "_fetch_panel_version"):
                        ver = await client._fetch_panel_version()
                        item["reachable"] = True
                        item["live_version"] = ver
                    elif hasattr(client, "_ensure_session"):
                        await client._ensure_session()
                        item["reachable"] = True
                    else:
                        item["reachable"] = None
                        item["note"] = "Нет метода healthcheck, только данные БД"
                except Exception as e:
                    item["reachable"] = False
                    item["error"] = str(e)[:300]
                results.append(item)
            return _ok(results)

        if name == "set_referral_coefficient":
            from database.db_users import get_user_by_telegram_id, set_user_referral_coefficient

            tid = int(args["telegram_id"])
            coef = float(args["coefficient"])
            u = get_user_by_telegram_id(tid)
            if not u:
                return _err("Пользователь не найден")
            uid = int(u.get("id") or u.get("user_id"))
            ok = set_user_referral_coefficient(uid, coef)
            return _ok({"telegram_id": tid, "user_id": uid, "coefficient": coef, "saved": bool(ok)})

        if name == "get_user_payments_stats":
            from database.db_users import get_user_by_telegram_id
            from database.db_payments import get_user_payments_stats

            tid = int(args["telegram_id"])
            u = get_user_by_telegram_id(tid)
            if not u:
                return _err("Пользователь не найден")
            uid = int(u.get("id") or u.get("user_id"))
            return _ok(get_user_payments_stats(uid))

        return _err(f"Неизвестный phase4 tool: {name}")
    except Exception as e:
        logger.exception("phase4 %s", name)
        return _err(str(e))
