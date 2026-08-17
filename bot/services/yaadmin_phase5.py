"""
YaAdmin Phase5
Просмотр и диагностика inbound 3X-ui
"""

from __future__ import annotations

import json
import logging

from bot.services.panels.xui import XUIClient
from database.db_servers import get_active_servers

logger = logging.getLogger(__name__)


def _ok(data):
    return json.dumps(
        {"ok": True, "data": data},
        ensure_ascii=False,
        default=str,
    )


def _err(msg):
    return json.dumps(
        {"ok": False, "error": str(msg)},
        ensure_ascii=False,
    )


PHASE5_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_inbounds",
            "description": "Список inbound панели 3X-ui",
            "parameters": {
                "type": "object",
                "properties": {}
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inbound",
            "description": "Получить inbound по ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "inbound_id": {
                        "type": "integer"
                    }
                },
                "required": ["inbound_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inbound_health",
            "description": "Проверить состояние inbound",
            "parameters": {
                "type": "object",
                "properties": {
                    "inbound_id": {
                        "type": "integer"
                    }
                },
                "required": ["inbound_id"],
            },
        },
    },
]


async def _client():
    servers = get_active_servers()

    if not servers:
        raise RuntimeError("Нет активных серверов")

    server = servers[0]

    return XUIClient(
        base_url=server["panel_url"],
        username=server["panel_login"],
        password=server["panel_password"],
    )


async def execute_phase5_tool(name: str, args: dict):

    try:

        client = await _client()

        if name == "list_inbounds":

            inbounds = await client.get_inbounds(include_ignored=True)

            result = []

            for ib in inbounds:

                settings = client._load_json_field(
                    ib.get("settings", "{}")
                )

                result.append(
                    {
                        "id": ib.get("id"),
                        "remark": ib.get("remark"),
                        "protocol": ib.get("protocol"),
                        "port": ib.get("port"),
                        "enable": ib.get("enable"),
                        "clients": len(
                            settings.get("clients", [])
                        ),
                        "tag": ib.get("tag"),
                    }
                )

            return _ok(result)

        if name == "get_inbound":

            inbound_id = int(args["inbound_id"])

            for ib in await client.get_inbounds(include_ignored=True):
                if int(ib["id"]) == inbound_id:
                    return _ok(ib)

            return _err("Inbound не найден")

        if name == "check_inbound_health":

            inbound_id = int(args["inbound_id"])

            for ib in await client.get_inbounds(include_ignored=True):

                if int(ib["id"]) != inbound_id:
                    continue

                settings = client._load_json_field(
                    ib.get("settings", "{}")
                )

                stream = client._load_json_field(
                    ib.get("streamSettings", "{}")
                )

                security = stream.get("security")

                reality = (
                    security == "reality"
                )

                tls = (
                    security == "tls"
                )

                result = {

                    "status": "online",

                    "id": ib.get("id"),

                    "remark": ib.get("remark"),

                    "protocol": ib.get("protocol"),

                    "port": ib.get("port"),

                    "enabled": ib.get("enable"),

                    "clients": len(
                        settings.get("clients", [])
                    ),

                    "security": security,

                    "reality": reality,

                    "tls": tls,

                    "certificate": (
                        "configured"
                        if tls
                        else None
                    ),

                    "api": "ok",

                }

                return _ok(result)

            return _err("Inbound не найден")

        return _err(f"Неизвестный tool: {name}")

    except Exception as e:

        logger.exception(e)

        return _err(e)

