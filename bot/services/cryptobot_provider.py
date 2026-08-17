"""Register Crypto Pay as a native XFI custom payment provider."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from bot.utils.payment_provider_registry import register_payment_provider
from bot.services.cryptobot import check_cryptobot_invoice, create_cryptobot_invoice
from database.db_cryptobot import is_cryptobot_configured


def _enabled(currency: str):
    def predicate(context: Mapping[str, Any]) -> bool:
        if not is_cryptobot_configured():
            return False
        return str(context.get("base_currency") or "RUB").upper() == currency
    return predicate


async def _create(context: Mapping[str, Any]) -> Mapping[str, Any]:
    result = await create_cryptobot_invoice(
        order_id=str(context["order_id"]),
        amount=Decimal(str(context["charge_amount"])),
        fiat=str(context["charge_currency"]),
        description=str(context.get("description") or "XFI VPN"),
    )
    return result


async def _check(context: Mapping[str, Any]) -> Mapping[str, Any]:
    order = context.get("provider_order") or {}
    result = await check_cryptobot_invoice(
        invoice_id=str(context.get("provider_payment_id") or order.get("provider_payment_id") or ""),
        order_id=str(context.get("order_id") or ""),
        amount=Decimal(str(context.get("charge_amount") or "0")),
        fiat=str(context.get("charge_currency") or context.get("currency") or "RUB"),
    )
    return {
        "status": result.status,
        "provider_payment_id": str(context.get("provider_payment_id") or order.get("provider_payment_id") or ""),
        "metadata": dict(result.metadata),
    }


def register_cryptobot_providers() -> None:
    for provider_id, currency, title, label in (
        ("crypto_pay_rub", "RUB", "Crypto Pay", "💎 Crypto Pay (RUB)"),
        ("crypto_pay_usd", "USD", "Crypto Pay", "💎 Crypto Pay (USD)"),
    ):
        try:
            register_payment_provider(
                provider_id,
                create_payment=_create,
                check_payment=_check,
                title=title,
                label=label,
                currency=currency,
                minimum_amount_minor=100,
                auto_check_interval_seconds=180,
                supported_purposes=("key_purchase", "key_renewal", "balance_topup"),
                is_enabled=_enabled(currency),
                replace=True,
            )
        except Exception:
            # Importing the module must never prevent the bot from starting.
            pass


register_cryptobot_providers()

__all__ = ["register_cryptobot_providers"]
