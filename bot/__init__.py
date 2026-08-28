"""Bot package bootstrap hooks.

The existing server-management UI stores one API token field. To avoid changing
the database schema and preserve all 3X-UI behavior, an explicit ``amnezia:``
prefix selects the Amnezia Admin API adapter at construction time.
"""


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
        return original_new(cls, server, *args, **kwargs)

    XUIClient.__new__ = staticmethod(_new)
    XUIClient._xfi_amnezia_hook_installed = True


_install_amnezia_constructor()
