"""Native Trial VPN claim service shared by Telegram and web flows."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_TRIAL_LOCKS: dict[int, asyncio.Lock] = {}


def _lock_for(telegram_id: int) -> asyncio.Lock:
    lock = _TRIAL_LOCKS.get(telegram_id)
    if lock is None:
        lock = asyncio.Lock()
        _TRIAL_LOCKS[telegram_id] = lock
    return lock


async def activate_native_trial(
    telegram_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    bot: Any = None,
) -> dict[str, Any]:
    """Create the same native trial key used by the Telegram bot.

    This intentionally uses XFI CONNECT's tariff/database/panel provisioning
    path instead of creating a separate 3X-UI trial client.
    """
    if not isinstance(telegram_id, int) or telegram_id <= 0:
        return {"ok": False, "reason": "invalid_telegram_id"}

    async with _lock_for(telegram_id):
        from database.requests import (
            get_or_create_user,
            has_used_trial,
            is_trial_enabled,
            get_trial_tariff_id,
            get_tariff_by_id,
            create_initial_vpn_key,
            create_pending_order,
            complete_order,
            update_vpn_key_config,
            find_order_by_order_id,
            get_key_details_for_user,
            get_user_by_telegram_id,
            get_servers_for_key,
        )
        from bot.services.vpn_api import (
            provision_client_on_server,
            get_subscription_url_for_key,
        )
        from bot.handlers.admin.users_keys import generate_unique_email

        if not is_trial_enabled():
            return {"ok": False, "reason": "trial_disabled"}
        tariff_id = get_trial_tariff_id()
        if tariff_id is None:
            return {"ok": False, "reason": "trial_not_configured"}
        if has_used_trial(telegram_id):
            return {"ok": False, "reason": "trial_already_used"}

        tariff = get_tariff_by_id(tariff_id)
        if not tariff:
            return {"ok": False, "reason": "trial_tariff_missing"}

        user, _ = get_or_create_user(
            telegram_id,
            username,
            first_name=first_name,
            last_name=last_name,
        )
        internal_user_id = user["id"]
        if user.get("is_banned"):
            return {"ok": False, "reason": "user_banned"}
        if has_used_trial(telegram_id):
            return {"ok": False, "reason": "trial_already_used"}

        servers = get_servers_for_key(tariff_id)
        if not servers:
            return {"ok": False, "reason": "no_active_servers"}
        server = servers[0]

        duration_days = int(tariff.get("duration_days") or 1)
        traffic_limit_bytes = int((tariff.get("traffic_limit_gb", 0) or 0) * 1024 ** 3)
        key_id = create_initial_vpn_key(
            internal_user_id,
            tariff_id,
            duration_days,
            traffic_limit=traffic_limit_bytes,
        )
        _, order_id = create_pending_order(
            user_id=internal_user_id,
            tariff_id=tariff_id,
            payment_type="trial",
            vpn_key_id=key_id,
        )
        complete_order(order_id)

        try:
            panel_email = generate_unique_email({
                "telegram_id": telegram_id,
                "username": username,
            })
            provisioned = await provision_client_on_server(
                server_id=server["id"],
                email=panel_email,
                total_gb=tariff.get("traffic_limit_gb", 0) or 0,
                expire_days=duration_days,
                limit_ip=tariff.get("max_ips", 1) or 1,
                enable=True,
                tg_id=str(telegram_id),
                sub_id=uuid.uuid4().hex,
                subscription_mode=True,
            )
            if not provisioned.complete and not provisioned.attached_inbound_ids:
                raise RuntimeError("Не удалось создать trial-клиента")
            if not provisioned.credential or provisioned.primary_inbound_id is None:
                raise RuntimeError("Панель не вернула данные trial-клиента")

            update_vpn_key_config(
                key_id=key_id,
                server_id=server["id"],
                panel_inbound_id=provisioned.primary_inbound_id,
                panel_email=panel_email,
                client_uuid=provisioned.credential,
                sub_id=provisioned.sub_id,
            )
            from bot.services.key_lifecycle import emit_key_lifecycle_event_safe
            await emit_key_lifecycle_event_safe(
                "key_configured",
                {
                    "key_id": key_id,
                    "user_id": internal_user_id,
                    "tariff_id": tariff_id,
                    "order_id": order_id,
                    "server_id": server["id"],
                    "panel_inbound_id": provisioned.primary_inbound_id,
                    "panel_email": panel_email,
                    "sub_id": provisioned.sub_id,
                    "subscription_mode": True,
                    "source": "web_trial",
                },
            )

            # Mark the native user trial only after successful panel provisioning.
            from database.requests import mark_trial_used
            mark_trial_used(internal_user_id)

            key_data = get_key_details_for_user(key_id, telegram_id)
            subscription_url = await get_subscription_url_for_key(key_data)
            if not subscription_url:
                raise RuntimeError("Не удалось построить subscription URL")

            if bot is not None:
                try:
                    from bot.services.notifications import notify_admins_payment
                    order = find_order_by_order_id(order_id)
                    if order:
                        await notify_admins_payment(bot, order)
                except Exception as exc:
                    logger.warning("Trial admin notification failed: %s", exc)

            return {
                "ok": True,
                "reason": "trial_issued",
                "telegram_id": telegram_id,
                "key_id": key_id,
                "order_id": order_id,
                "tariff_id": tariff_id,
                "server_id": server["id"],
                "expires_at": key_data.get("expires_at"),
                "subscription": subscription_url,
            }
        except Exception:
            logger.exception("Native web trial provisioning failed for telegram_id=%s", telegram_id)
            # The order/key remain auditable; the trial flag was not consumed.
            return {"ok": False, "reason": "provisioning_failed"}


__all__ = ["activate_native_trial"]
