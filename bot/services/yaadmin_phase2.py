"""Фаза 2: UI кнопки/медиа + черновик рассылки (без send)."""
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


PHASE2_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_page_media",
            "description": "Установить или очистить image/media страницы (Telegram file_id или пусто)",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_key": {"type": "string"},
                    "image": {"type": "string", "description": "file_id или пустая строка"},
                    "media_type": {"type": "string"},
                },
                "required": ["page_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_page_buttons",
            "description": "Полная замена JSON кнопок страницы (custom)",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_key": {"type": "string"},
                    "buttons_json": {"type": "string"},
                },
                "required": ["page_key", "buttons_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_page_button_text",
            "description": "Заменить текст кнопки на странице по старому тексту",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_key": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["page_key", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_broadcast_draft",
            "description": "Прочитать черновик рассылки (не отправляет)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_broadcast_message_draft",
            "description": "Сохранить текст/фото черновика рассылки. НЕ запускает рассылку.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "photo_file_id": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
]


def _page_buttons_raw(page: dict) -> Any:
    for key in ("buttons", "buttons_custom", "buttons_default"):
        if page.get(key) not in (None, ""):
            val = page[key]
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    return val
            return val
    return None


def _walk_replace_button_text(obj: Any, old: str, new: str) -> tuple[Any, int]:
    count = 0
    if isinstance(obj, list):
        out = []
        for item in obj:
            ni, c = _walk_replace_button_text(item, old, new)
            out.append(ni)
            count += c
        return out, count
    if isinstance(obj, dict):
        d = dict(obj)
        if d.get("text") == old:
            d["text"] = new
            count += 1
        for k, v in list(d.items()):
            if isinstance(v, (list, dict)):
                nv, c = _walk_replace_button_text(v, old, new)
                d[k] = nv
                count += c
        return d, count
    return obj, 0


async def execute_phase2_tool(name: str, args: dict) -> str:
    try:
        if name == "set_page_media":
            from database.db_pages import update_page_custom

            page_key = args["page_key"]
            image = args.get("image")
            if image is not None and str(image).strip() == "":
                image = None
            sig = inspect.signature(update_page_custom)
            params = set(sig.parameters)
            kwargs: dict[str, Any] = {}
            if "image" in params:
                kwargs["image"] = image
            elif "photo" in params:
                kwargs["photo"] = image
            if args.get("media_type") and "media_type" in params:
                kwargs["media_type"] = args["media_type"]
            if not kwargs:
                return _err("update_page_custom не принимает image/photo")
            update_page_custom(page_key, **kwargs)
            return _ok({"page_key": page_key, "image": image, "updated": True})

        if name == "set_page_buttons":
            from database.db_pages import update_page_custom

            page_key = args["page_key"]
            raw = args["buttons_json"]
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            buttons_val = json.dumps(parsed, ensure_ascii=False)
            if "buttons" not in inspect.signature(update_page_custom).parameters:
                return _err("update_page_custom без buttons")
            update_page_custom(page_key, buttons=buttons_val)
            return _ok({"page_key": page_key, "buttons_set": True})

        if name == "patch_page_button_text":
            from database.db_pages import get_page, update_page_custom

            page_key = args["page_key"]
            page = get_page(page_key)
            if not page:
                return _err(f"Страница {page_key} не найдена")
            buttons = _page_buttons_raw(page)
            if buttons is None:
                return _err("Нет buttons JSON на странице")
            new_buttons, n = _walk_replace_button_text(
                buttons, args["old_text"], args["new_text"]
            )
            if n == 0:
                return _err(f"Кнопка «{args['old_text']}» не найдена")
            if "buttons" not in inspect.signature(update_page_custom).parameters:
                return _err("update_page_custom без buttons")
            update_page_custom(
                page_key, buttons=json.dumps(new_buttons, ensure_ascii=False)
            )
            return _ok({"page_key": page_key, "replaced": n})

        if name == "get_broadcast_draft":
            try:
                from bot.services.broadcast_content import load_broadcast_content
                return _ok(load_broadcast_content())
            except Exception as e:
                return _err(f"broadcast: {e}")

        if name == "set_broadcast_message_draft":
            try:
                from bot.services.broadcast_content import save_message_content
                save_message_content(args["text"], args.get("photo_file_id") or None)
                return _ok({"saved": True, "note": "Черновик сохранён, рассылка НЕ запущена"})
            except Exception as e:
                return _err(f"save draft: {e}")

        return _err(f"Неизвестный tool: {name}")
    except Exception as e:
        logger.exception("phase2 %s", name)
        return _err(str(e))
