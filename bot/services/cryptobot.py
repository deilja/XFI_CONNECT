"""Safe Crypto Pay API client for XFI_CONNECT."""
from __future__ import annotations

import asyncio
import weakref
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlparse

import aiohttp

from database.db_cryptobot import get_cryptobot_token
from bot.services.payment_api import (
    PaymentApiRateLimitError,
    PaymentApiResponseError,
    PaymentApiTransientError,
    payment_client_timeout,
    run_payment_api_operation,
)

CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"
CRYPTOBOT_INVOICE_EXPIRES_SECONDS = 3600
CRYPTOBOT_PROVIDER_ID = "crypto_pay"
_LOCKS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()

@dataclass(frozen=True)
class CryptoBotInvoiceCheck:
    status: str
    metadata: Mapping[str, Any]


def cryptobot_lifecycle_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[loop] = lock
    return lock


def _token(token: str | None = None) -> str:
    value = str(token if token is not None else get_cryptobot_token()).strip()
    if not value or any(ord(c) < 32 for c in value):
        raise PaymentApiResponseError("Crypto Pay API token is not configured")
    return value


async def _request(method: str, *, params: Mapping[str, Any] | None = None, token: str | None = None, retry: bool = True, order_id: str | None = None) -> Any:
    api_token = _token(token)

    async def call() -> Any:
        headers = {
            "Crypto-Pay-API-Token": api_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(timeout=payment_client_timeout()) as session:
            async with session.post(f"{CRYPTOBOT_API_URL}/{method}", headers=headers, json=dict(params or {})) as response:
                try:
                    payload = await response.json(content_type=None)
                except Exception as error:
                    if response.status >= 500:
                        raise PaymentApiTransientError(f"Crypto Pay HTTP {response.status}: invalid JSON") from error
                    raise PaymentApiResponseError(f"Crypto Pay HTTP {response.status}: invalid JSON") from error
                if response.status == 429:
                    raise PaymentApiRateLimitError("Crypto Pay HTTP 429")
                if response.status >= 500:
                    raise PaymentApiTransientError(f"Crypto Pay HTTP {response.status}")
                if response.status < 200 or response.status >= 300:
                    raise PaymentApiResponseError(f"Crypto Pay HTTP {response.status}")
                if not isinstance(payload, dict) or payload.get("ok") is not True:
                    error_text = str((payload or {}).get("error") or "Crypto Pay rejected the request") if isinstance(payload, dict) else "Crypto Pay returned invalid response"
                    raise PaymentApiResponseError(error_text[:200].replace("\n", " "))
                return payload.get("result")

    return await run_payment_api_operation(provider=CRYPTOBOT_PROVIDER_ID, operation=method, order_id=order_id, call=call, retry=retry)


async def validate_cryptobot_token(token: str) -> Mapping[str, Any]:
    result = await _request("getMe", token=token, retry=True)
    if not isinstance(result, dict):
        raise PaymentApiResponseError("Crypto Pay getMe returned invalid app data")
    return result


async def create_cryptobot_invoice(*, order_id: str, amount: Decimal, fiat: str, description: str) -> dict[str, Any]:
    normalized_amount = _positive_decimal(amount)
    normalized_fiat = str(fiat).strip().upper()
    if normalized_fiat not in {"RUB", "USD"}:
        raise ValueError("Crypto Pay supports RUB and USD base currencies")
    result = await _request(
        "createInvoice",
        params={
            "currency_type": "fiat",
            "fiat": normalized_fiat,
            "amount": _decimal_text(normalized_amount),
            "description": str(description or "")[:1024],
            "payload": str(order_id),
            "expires_in": CRYPTOBOT_INVOICE_EXPIRES_SECONDS,
        },
        retry=False,
        order_id=str(order_id),
    )
    if not isinstance(result, dict):
        raise PaymentApiResponseError("Crypto Pay createInvoice returned invalid data")
    invoice_id = str(result.get("invoice_id") or "").strip()
    payment_url = str(result.get("bot_invoice_url") or "").strip()
    parsed = urlparse(payment_url)
    if not invoice_id or parsed.scheme != "https" or not parsed.netloc:
        raise PaymentApiResponseError("Crypto Pay returned invalid invoice identity or URL")
    _validate_invoice(result, invoice_id=invoice_id, order_id=str(order_id), amount=normalized_amount, fiat=normalized_fiat)
    return {
        "provider_payment_id": invoice_id,
        "payment_url": payment_url,
        "status": "pending",
        "metadata": _safe_metadata(result),
    }


async def check_cryptobot_invoice(*, invoice_id: str, order_id: str, amount: Decimal, fiat: str) -> CryptoBotInvoiceCheck:
    result = await _request("getInvoices", params={"invoice_ids": str(invoice_id)}, retry=True, order_id=order_id)
    items = result if isinstance(result, list) else result.get("items", []) if isinstance(result, dict) else []
    invoice = next((x for x in items if isinstance(x, dict) and str(x.get("invoice_id")) == str(invoice_id)), None)
    if invoice is None:
        raise PaymentApiResponseError("Crypto Pay invoice was not found")
    _validate_invoice(invoice, invoice_id=str(invoice_id), order_id=str(order_id), amount=_positive_decimal(amount), fiat=str(fiat).upper())
    raw_status = str(invoice.get("status") or "").casefold()
    status = {"paid": "succeeded", "active": "pending", "expired": "canceled"}.get(raw_status)
    if status is None:
        raise PaymentApiResponseError("Crypto Pay invoice status is unsupported")
    return CryptoBotInvoiceCheck(status=status, metadata=_safe_metadata(invoice))


def _validate_invoice(invoice: Mapping[str, Any], *, invoice_id: str, order_id: str, amount: Decimal, fiat: str) -> None:
    if str(invoice.get("invoice_id") or "") != invoice_id:
        raise PaymentApiResponseError("Crypto Pay invoice_id mismatch")
    if str(invoice.get("payload") or "") != order_id:
        raise PaymentApiResponseError("Crypto Pay invoice payload mismatch")
    if str(invoice.get("currency_type") or "").casefold() != "fiat":
        raise PaymentApiResponseError("Crypto Pay invoice currency_type mismatch")
    if str(invoice.get("fiat") or "").upper() != fiat:
        raise PaymentApiResponseError("Crypto Pay invoice fiat mismatch")
    try:
        actual = Decimal(str(invoice.get("amount")))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise PaymentApiResponseError("Crypto Pay invoice amount is invalid") from error
    if not actual.is_finite() or actual != amount:
        raise PaymentApiResponseError("Crypto Pay invoice amount mismatch")


def _safe_metadata(invoice: Mapping[str, Any]) -> dict[str, Any]:
    allowed = ("currency_type", "fiat", "amount", "paid_asset", "paid_amount", "paid_fiat_rate", "paid_usd_rate", "fee_asset", "fee_amount", "created_at", "expiration_date", "paid_at")
    metadata = {k: invoice[k] for k in allowed if invoice.get(k) is not None and isinstance(invoice.get(k), (str, int, float, bool))}
    metadata["invoice_id"] = str(invoice.get("invoice_id") or "")
    return metadata


def _positive_decimal(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Crypto Pay amount must be decimal") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("Crypto Pay amount must be positive")
    return parsed


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


__all__ = ["CRYPTOBOT_PROVIDER_ID", "CryptoBotInvoiceCheck", "check_cryptobot_invoice", "create_cryptobot_invoice", "cryptobot_lifecycle_lock", "validate_cryptobot_token"]
