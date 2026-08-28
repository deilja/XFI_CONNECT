"""Amnezia Admin API adapter for XFI_CONNECT.

The adapter intentionally keeps the existing XFI_CONNECT panel contract.  One
Amnezia client is represented as a synthetic inbound (id=0), while the actual
profile is created and managed through Amnezia Admin API /clients.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from .base import (
    BaseVPNClient,
    PanelDatabaseBackup,
    PanelInboundDescriptor,
    PanelServerSnapshot,
    PanelClientState,
    VPNAPIError,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_RETRIES = 3
RETRY_DELAY = 1.5
AMNEZIA_PROFILE = "amnezia_admin_api"


class AmneziaClient(BaseVPNClient):
    """XFI_CONNECT-compatible client for Amnezia Admin API."""

    def __init__(self, server: dict):
        self.server = server
        self.base_url = self._build_base_url(server)
        self.api_key = str(server.get("api_token") or "").strip()
        self.protocol = str(server.get("amnezia_protocol") or "amneziawg2").strip()
        self._session: Optional[aiohttp.ClientSession] = None

    @staticmethod
    def _build_base_url(server: dict) -> str:
        protocol = str(server.get("protocol") or "http").strip()
        host = str(server.get("host") or "").strip()
        port = int(server.get("port") or 80)
        path = str(server.get("web_base_path") or "/").strip()
        if not path.startswith("/"):
            path = "/" + path
        if path != "/" and not path.endswith("/"):
            path += "/"
        return f"{protocol}://{host}:{port}{path.rstrip('/')}"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
                connector=aiohttp.TCPConnector(
                    ssl=str(self.server.get("protocol", "http")).lower() == "https"
                ),
            )
        return self._session

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        last_error = "unknown error"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.request(method, url, **kwargs) as response:
                    text = await response.text()
                    if 200 <= response.status < 300:
                        if not text:
                            return {}
                        try:
                            return await response.json()
                        except (aiohttp.ContentTypeError, ValueError):
                            return text
                    last_error = f"HTTP {response.status}: {text[:300]}"
                    if response.status < 500:
                        raise VPNAPIError(last_error)
            except VPNAPIError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = str(exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)
        raise VPNAPIError(f"Amnezia Admin API недоступен: {last_error}")

    async def login(self) -> bool:
        return await self.health_check()

    async def health_check(self) -> bool:
        try:
            await self._request("GET", "/healthz")
            return True
        except Exception as exc:
            logger.warning("Amnezia healthcheck failed: %s", exc)
            return False

    async def get_all_clients(self) -> dict:
        result = await self._request("GET", "/clients")
        return result if isinstance(result, dict) else {"total": 0, "items": []}

    async def create_user(self, client_name: str) -> dict:
        result = await self._request(
            "POST",
            "/clients",
            json={"clientName": client_name, "protocol": self.protocol},
        )
        if not isinstance(result, dict):
            raise VPNAPIError("Amnezia API returned an invalid client response")
        return result

    async def update_user(self, client_id: str, **kwargs) -> bool:
        payload = {"clientId": client_id, **kwargs}
        try:
            await self._request("PATCH", "/clients", json=payload)
            return True
        except Exception as exc:
            logger.warning("Amnezia client update failed: %s", exc)
            return False

    async def delete_user(self, client_id: str) -> bool:
        try:
            await self._request(
                "DELETE",
                "/clients",
                json={"clientId": client_id, "protocol": self.protocol},
            )
            return True
        except Exception as exc:
            logger.warning("Amnezia client deletion failed: %s", exc)
            return False

    async def get_inbounds(self, include_ignored: bool = False) -> List[Dict[str, Any]]:
        """Expose one synthetic inbound so existing server/key UI can select Amnezia."""
        return [{
            "id": 0,
            "protocol": self.protocol,
            "remark": "AmneziaVPN",
            "tag": "amnezia",
            "port": int(self.server.get("port") or 0),
            "settings": {},
            "streamSettings": {},
            "tlsFlowCapable": False,
        }]

    async def get_subscription_inbounds(self, include_ignored: bool = False):
        return await self.get_inbounds(include_ignored=include_ignored)

    async def add_client(
        self,
        inbound_id: int,
        email: str,
        total_gb: int = 0,
        expire_days: int = 30,
        limit_ip: int = 1,
        enable: bool = True,
        tg_id: str = "",
        flow: str = "",
        sub_id: Optional[str] = None,
        total_gb_bytes: Optional[int] = None,
        expiry_time_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        if int(inbound_id) != 0:
            raise VPNAPIError("Amnezia adapter accepts only synthetic inbound id 0")
        result = await self.create_user(email)
        client = result.get("client") or {}
        client_id = str(client.get("id") or client.get("clientId") or "")
        config = client.get("config")
        if not client_id:
            raise VPNAPIError("Amnezia API did not return client id")
        if not enable:
            await self.update_user(client_id, status="disabled")
        return {
            "uuid": client_id,
            "client_uuid": client_id,
            "config": config,
            "protocol": client.get("protocol") or self.protocol,
            "sub_id": str(sub_id or ""),
            "email": email,
        }

    async def get_client_config(self, email: str) -> Optional[Dict[str, Any]]:
        clients = await self.get_all_clients()
        for item in clients.get("items", []):
            if item.get("username") != email:
                continue
            for peer in item.get("peers", []):
                if peer.get("config"):
                    return {
                        "config": peer["config"],
                        "uuid": peer.get("id") or peer.get("publicKey") or email,
                        "protocol": peer.get("protocol") or self.protocol,
                    }
            if item.get("config"):
                return {
                    "config": item["config"],
                    "uuid": item.get("id") or email,
                    "protocol": item.get("protocol") or self.protocol,
                }
        return None

    async def get_client_links(self, email: str) -> List[str]:
        config = await self.get_client_config(email)
        value = config.get("config") if config else None
        return [str(value)] if value else []

    async def get_client_stats(self, email: str, resolve_inbound: bool = True) -> Optional[Dict[str, Any]]:
        clients = await self.get_all_clients()
        for item in clients.get("items", []):
            if item.get("username") == email:
                for peer in item.get("peers", []):
                    return dict(peer)
        return None

    async def get_server_status(self) -> Dict[str, Any]:
        try:
            server = await self._request("GET", "/server")
            return {"online": True, **(server if isinstance(server, dict) else {})}
        except Exception as exc:
            return {"online": False, "error": str(exc)}

    async def get_stats(self) -> Dict[str, Any]:
        if not await self.health_check():
            return {"online": False, "online_clients": 0, "total_traffic_bytes": 0}
        clients = await self.get_all_clients()
        online = 0
        traffic = 0
        for item in clients.get("items", []):
            for peer in item.get("peers", []):
                if peer.get("online") or peer.get("status") == "online":
                    online += 1
                tr = peer.get("traffic") or {}
                traffic += int(tr.get("received", 0) or 0) + int(tr.get("sent", 0) or 0)
        load = await self._request("GET", "/server/load")
        return {
            "online": True,
            "online_clients": online,
            "total_traffic_bytes": traffic,
            "cpu_percent": load.get("cpu") if isinstance(load, dict) else None,
            "ram_percent": load.get("ram") if isinstance(load, dict) else None,
        }

    async def get_online_clients_count(self) -> int:
        return int((await self.get_stats()).get("online_clients", 0))

    async def get_nodes(self) -> List[Dict[str, Any]]:
        return []

    async def get_inbound_flow(self, inbound_id: int) -> str:
        return ""

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        return await self.delete_user(str(client_uuid))

    async def reset_client_traffic(self, inbound_id: int, email: str) -> bool:
        # Amnezia Admin API does not expose the 3X-UI reset semantics.
        return False

    async def update_client_traffic_limit(self, inbound_id: int, client_uuid: str, email: str, total_gb: int) -> bool:
        return False

    async def update_client_limit(self, inbound_id: int, client_uuid: str, email: str, total_gb_bytes: int) -> bool:
        return False

    async def disable_reset_for_all_clients(self) -> int:
        return 0

    async def extend_client_expiry(self, inbound_id: int, client_uuid: str, email: str, days: int) -> bool:
        # Amnezia API accepts PATCH /clients. We preserve the current expiry when
        # available and extend it in milliseconds.
        clients = await self.get_all_clients()
        current = 0
        for item in clients.get("items", []):
            if item.get("username") != email:
                continue
            for peer in item.get("peers", []):
                current = int(peer.get("expiryTime") or peer.get("expiry_time") or 0)
                client_uuid = str(peer.get("id") or peer.get("publicKey") or client_uuid)
                break
        base = max(current, int(datetime.now(timezone.utc).timestamp() * 1000))
        return await self.update_user(str(client_uuid), expiryTime=base + int(days) * 86400000)

    async def get_subscription_link(self, sub_id: str) -> Optional[str]:
        # Amnezia profiles are delivered directly as vpn:// configuration strings.
        return str(sub_id) if sub_id else None

    async def get_database_backup(self) -> PanelDatabaseBackup:
        raise VPNAPIError("Database backup is not supported by Amnezia Admin API")

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get_sync_snapshot(self, subscription_mode: bool = False) -> PanelServerSnapshot:
        clients = await self.get_all_clients()
        states: Dict[str, PanelClientState] = {}
        for item in clients.get("items", []):
            username = str(item.get("username") or "").strip()
            if not username:
                continue
            state = PanelClientState(
                email=username,
                source=AMNEZIA_PROFILE,
                details_complete=True,
            )
            for peer in item.get("peers", []):
                state.inbound_ids.add(0)
                state.placements[0] = dict(peer)
                state.client = dict(peer)
                tr = peer.get("traffic") or {}
                state.traffic_used += int(tr.get("received", 0) or 0) + int(tr.get("sent", 0) or 0)
            states[username.lower()] = state
        return PanelServerSnapshot(
            api_profile=AMNEZIA_PROFILE,
            inbounds=await self.get_inbounds(include_ignored=True),
            clients=states,
        )

    async def provision_client(self, **kwargs):
        # Use BaseVPNClient's canonical one-client provisioning path.
        return await super().provision_client(**kwargs)
