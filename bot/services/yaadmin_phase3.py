"""
Фаза 3: тарифы/промо (read + soft edit) + превью sync (без авто-apply).
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Одноразовые токены подтверждения опасных операций (в памяти процесса)
_PENDING: dict[str, dict[str, Any]] = {}


def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


PHASE3_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tariffs",
            "description": "Список тарифов бота",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tariff",
            "description": "Тариф по id",
            "parameters": {
                "type": "object",
                "properties": {"tariff_id": {"type": "integer"}},
                "required": ["tariff_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_tariff_price",
            "description": "Изменить цену тарифа (базовая валюта бота, осторожно)",
            "parameters": {
                "type": "object",
                "properties": {
                    "tariff_id": {"type": "integer"},
                    "price": {"type": "number"},
                },
                "required": ["tariff_id", "price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_promo_codes",
            "description": "Список промокодов (кратко)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_panel_sync",
            "description": "Превью синхронизации ключей с 3X-UI. НЕ применяет изменения.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_panel_sync",
            "description": "Применить ранее полученное превью sync. Нужен confirm_token из preview_panel_sync.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirm_token": {"type": "string"},
                },
                "required": ["confirm_token"],
            },
        },
    },
]


def _list_tariffs_safe() -> list:
    try:
        from database.db_tariffs import get_all_tariffs
        return get_all_tariffs()
    except ImportError:
        pass
    try:
        from database.db_tariffs import get_tariffs
        return get_tariffs()
    except Exception:
        pass
    try:
        from database import requests as req
        if hasattr(req, "get_all_tariffs"):
            return req.get_all_tariffs()
    except Exception:
        pass
    raise RuntimeError("Не найдена функция списка тарифов")


def _get_tariff_safe(tid: int) -> dict | None:
    try:
        from database.db_tariffs import get_tariff_by_id
        return get_tariff_by_id(tid)
    except ImportError:
        pass
    try:
        from database.db_tariffs import get_tariff
        return get_tariff(tid)
    except Exception:
        pass
    for t in _list_tariffs_safe():
        if int(t.get("id") or 0) == tid:
            return t
    return None


def _update_tariff_price_safe(tid: int, price: float) -> bool:
    try:
        from database.db_tariffs import update_tariff
        return bool(update_tariff(tid, price=price))
    except TypeError:
        try:
            from database.db_tariffs import update_tariff
            return bool(update_tariff(tid, **{"price": price}))
        except Exception:
            pass
    except Exception as e:
        logger.warning("update_tariff: %s", e)
    try:
        from database.db_tariffs import set_tariff_price
        return bool(set_tariff_price(tid, price))
    except Exception:
        raise RuntimeError("Не удалось обновить цену тарифа — проверь db_tariffs")


async def execute_phase3_tool(name: str, args: dict) -> str:
    try:
        if name == "list_tariffs":
            tariffs = _list_tariffs_safe()
            out = []
            for t in tariffs:
                out.append({
                    "id": t.get("id"),
                    "name": t.get("name") or t.get("title"),
                    "price": t.get("price"),
                    "days": t.get("days") or t.get("duration_days"),
                    "traffic_gb": t.get("traffic_gb") or t.get("traffic_limit"),
                    "is_active": t.get("is_active", t.get("enabled")),
                })
            return _ok(out)

        if name == "get_tariff":
            t = _get_tariff_safe(int(args["tariff_id"]))
            return _ok(t) if t else _err("Тариф не найден")

        if name == "update_tariff_price":
            tid = int(args["tariff_id"])
            price = float(args["price"])
            ok = _update_tariff_price_safe(tid, price)
            return _ok({"tariff_id": tid, "price": price, "updated": bool(ok)})

        if name == "list_promo_codes":
            try:
                from database.db_promotions import get_promo_codes
                codes = get_promo_codes()
            except Exception:
                try:
                    from database.db_promotions import list_promo_codes
                    codes = list_promo_codes()
                except Exception as e:
                    return _err(f"promotions: {e}")
            out = []
            for c in (codes or [])[:50]:
                out.append({
                    "id": c.get("id"),
                    "code": c.get("code"),
                    "discount": c.get("discount") or c.get("percent") or c.get("value"),
                    "is_active": c.get("is_active"),
                })
            return _ok(out)

        if name == "preview_panel_sync":
            # Только описание + токен. Реальный diff зависит от вашей panel_sync API.
            import uuid
            token = uuid.uuid4().hex[:12]
            summary = {
                "note": (
                    "Превью: полная синхронизация ключей с панелью в UI админки "
                    "безопаснее (Пользователи → синхронизация с подтверждением). "
                    "Local YaAdmin не применяет sync без confirm_panel_sync."
                ),
                "confirm_token": token,
                "how": "Вызови confirm_panel_sync с этим confirm_token только если уверен.",
            }
            # Попытка мягкого read-only snapshot, если есть
            try:
                from database.db_keys import get_all_panel_sync_keys
                keys = get_all_panel_sync_keys()
                summary["keys_tracked"] = len(keys or [])
            except Exception:
                summary["keys_tracked"] = None
            try:
                from database.db_servers import get_active_servers
                summary["active_servers"] = len(get_active_servers() or [])
            except Exception:
                pass
            _PENDING[token] = {"action": "panel_sync", "created": True}
            return _ok(summary)

        if name == "confirm_panel_sync":
            token = str(args.get("confirm_token") or "")
            pending = _PENDING.pop(token, None)
            if not pending:
                return _err("Неверный или просроченный confirm_token. Сначала preview_panel_sync.")
            # Намеренно НЕ вызываем разрушающий full-sync автоматически.
            # Админка делает preview + кнопка «Применить».
            return _ok({
                "applied": False,
                "reason": (
                    "Авто-apply sync отключён в Local YaAdmin из соображений безопасности. "
                    "Открой админку → Пользователи → синхронизация с панелью → превью → Применить."
                ),
            })

        return _err(f"Неизвестный phase3 tool: {name}")
    except Exception as e:
        logger.exception("phase3 %s", name)
        return _err(str(e))
