"""Bot package bootstrap hooks.

The existing server-management UI stores one API token field. To avoid changing
the database schema and preserve all 3X-UI behavior, an explicit ``amnezia:``
prefix selects the Amnezia Admin API adapter at construction time.
"""


async def _amnezia_update_client_full(
    self,
    *,
    inbound_id: int,
    client_uuid: str,
    email: str,
    expiry_time_ms: int = 0,
    total_gb_bytes: int = 0,
    enable: bool = True,
    limit_ip: int = 1,
    sub_id=None,
    flow=None,
    **kwargs,
) -> bool:
    """Map XFI's generic update operation to Amnezia's PATCH /clients."""
    payload = {"status": "active" if enable else "disabled"}
    if expiry_time_ms is not None:
        payload["expiryTime"] = int(expiry_time_ms or 0)
    return await self.update_user(str(client_uuid), **payload)


async def _amnezia_stats_with_flat_traffic(self, email: str, resolve_inbound: bool = True):
    """Expose Amnezia peer traffic in XFI's normalized counter shape."""
    result = await self._xfi_original_get_client_stats(email, resolve_inbound=resolve_inbound)
    if not isinstance(result, dict):
        return result
    traffic = result.get("traffic") or {}
    up = int(traffic.get("sent", traffic.get("up", result.get("up", 0))) or 0)
    down = int(traffic.get("received", traffic.get("down", result.get("down", 0))) or 0)
    normalized = dict(result)
    normalized.update({
        "up": up,
        "down": down,
        "source": "clients_api_global",
        "totalGB": int(result.get("totalGB", result.get("total", 0)) or 0),
        "expiryTime": int(result.get("expiryTime", result.get("expiry_time", 0)) or 0),
    })
    return normalized


def _install_amnezia_constructor():
    from .services.panels.xui import XUIClient
    from .services.panels.amnezia import AmneziaClient, AMNEZIA_PROFILE

    if getattr(XUIClient, "_xfi_amnezia_hook_installed", False):
        return

    original_new = getattr(XUIClient, "__new__", object.__new__)

    def _new(cls, server=None, *args, **kwargs):
        data = dict(server or {}) if isinstance(server, dict) else server
        token = str((data or {}).get("api_token") or "").strip()
        profile = str((data or {}).get("panel_api_profile") or "").strip().lower()
        if profile == AMNEZIA_PROFILE or token.startswith("amnezia:"):
            if isinstance(data, dict) and token.startswith("amnezia:"):
                data["api_token"] = token.split(":", 1)[1].strip()
            return AmneziaClient(data)
        if original_new is object.__new__:
            return original_new(cls)
        return original_new(cls, server, *args, **kwargs)

    XUIClient.__new__ = staticmethod(_new)
    XUIClient._xfi_amnezia_hook_installed = True

    AmneziaClient.api_profile = AMNEZIA_PROFILE
    if not hasattr(AmneziaClient, "_xfi_original_get_client_stats"):
        AmneziaClient._xfi_original_get_client_stats = AmneziaClient.get_client_stats
        AmneziaClient.get_client_stats = _amnezia_stats_with_flat_traffic
    AmneziaClient.update_client_full = _amnezia_update_client_full


_install_amnezia_constructor()
