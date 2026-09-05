"""HTTP endpoints for custom payment providers and Trial VPN events."""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

from aiohttp import web

from database.requests import get_setting

logger = logging.getLogger(__name__)
WEBHOOKS_ENABLED_SETTING = 'custom_payment_webhooks_enabled'
WEBHOOKS_HOST_SETTING = 'custom_payment_webhooks_host'
WEBHOOKS_PORT_SETTING = 'custom_payment_webhooks_port'
WEBHOOKS_PATH_PREFIX_SETTING = 'custom_payment_webhooks_path_prefix'
DEFAULT_WEBHOOKS_HOST = '127.0.0.1'
DEFAULT_WEBHOOKS_PORT = 8088
DEFAULT_WEBHOOKS_PATH_PREFIX = '/custom-payment-webhook'
WEBHOOK_SECRET_HEADER = 'X-Yadreno-Webhook-Secret'
TRIAL_WEBHOOK_PATH = '/trial-vpn'
TRIAL_WEBHOOK_SECRET_ENV = 'TRIAL_VPN_WEBHOOK_SECRET'
BOT_APP_KEY = web.AppKey('custom_payment_webhook_bot', Any)


@dataclass
class CustomPaymentWebhookServer:
    runner: web.AppRunner
    host: str
    port: int
    path_prefix: str

    async def stop(self) -> None:
        await self.runner.cleanup()


async def start_custom_payment_webhook_server(bot: Any) -> CustomPaymentWebhookServer | None:
    payment_enabled = is_custom_payment_webhook_server_enabled()
    trial_enabled = bool(os.getenv(TRIAL_WEBHOOK_SECRET_ENV, '').strip())
    if not payment_enabled and not trial_enabled:
        logger.info("Custom payment/Trial VPN webhook server выключен")
        return None
    host = get_custom_payment_webhook_host()
    port = get_custom_payment_webhook_port()
    path_prefix = get_custom_payment_webhook_path_prefix()
    app = create_custom_payment_webhook_app(bot, path_prefix=path_prefix)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, host=host, port=port).start()
    except Exception:
        await runner.cleanup()
        raise
    logger.info("Webhook server запущен: http://%s:%s%s", host, port, path_prefix)
    return CustomPaymentWebhookServer(runner=runner, host=host, port=port, path_prefix=path_prefix)


def create_custom_payment_webhook_app(bot: Any, *, path_prefix: str | None = None) -> web.Application:
    normalized_prefix = _normalize_path_prefix(path_prefix or DEFAULT_WEBHOOKS_PATH_PREFIX)
    app = web.Application(client_max_size=1024 * 1024)
    app[BOT_APP_KEY] = bot
    app.router.add_get(f'{normalized_prefix}/health', _health_handler)
    app.router.add_post(f'{normalized_prefix}/{{provider_id}}', _payment_webhook_handler)
    app.router.add_post(f'{normalized_prefix}{TRIAL_WEBHOOK_PATH}', _trial_vpn_webhook_handler)
    app.router.add_post(f'{normalized_prefix}{TRIAL_WEBHOOK_PATH}/claim', _trial_vpn_claim_handler)
    return app


def is_custom_payment_webhook_server_enabled() -> bool:
    return str(get_setting(WEBHOOKS_ENABLED_SETTING, '0') or '').strip() == '1'


def get_custom_payment_webhook_host() -> str:
    return str(get_setting(WEBHOOKS_HOST_SETTING, DEFAULT_WEBHOOKS_HOST) or DEFAULT_WEBHOOKS_HOST).strip() or DEFAULT_WEBHOOKS_HOST


def get_custom_payment_webhook_port() -> int:
    try:
        port = int(get_setting(WEBHOOKS_PORT_SETTING, str(DEFAULT_WEBHOOKS_PORT)) or DEFAULT_WEBHOOKS_PORT)
    except (TypeError, ValueError):
        return DEFAULT_WEBHOOKS_PORT
    return port if 0 < port <= 65535 else DEFAULT_WEBHOOKS_PORT


def get_custom_payment_webhook_path_prefix() -> str:
    return _normalize_path_prefix(get_setting(WEBHOOKS_PATH_PREFIX_SETTING, DEFAULT_WEBHOOKS_PATH_PREFIX) or DEFAULT_WEBHOOKS_PATH_PREFIX)


async def _health_handler(request: web.Request) -> web.Response:
    return web.json_response({'ok': True})


async def _trial_vpn_webhook_handler(request: web.Request) -> web.Response:
    secret = os.getenv(TRIAL_WEBHOOK_SECRET_ENV, '').strip()
    if not secret:
        return web.json_response({'ok': False, 'reason': 'not_configured'}, status=503)
    provided = request.headers.get('X-XFI-Webhook-Secret', '')
    if not hmac.compare_digest(provided, secret):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({'ok': False, 'reason': 'invalid_json'}, status=400)
    if payload.get('type') != 'trial_issued':
        return web.json_response({'ok': False, 'reason': 'unsupported_event'}, status=400)
    bot = request.app[BOT_APP_KEY]
    total, hours, expires = payload.get('totalTrials', '?'), payload.get('hours', '?'), payload.get('expiresAt', '?')
    logger.info("Trial VPN event: total=%s hours=%s expires=%s", total, hours, expires)
    try:
        from bot.services.ai_admin_ids import get_ai_admin_ids
        text = f"<b>XFI CONNECT — новый VPN-тест</b>\n\nСрок: {hours} ч.\nИстекает: {expires}\nВсего тестов: <b>{total}</b>"
        for admin_id in get_ai_admin_ids():
            try:
                await bot.send_message(admin_id, text, parse_mode='HTML')
            except Exception as exc:
                logger.warning("Trial VPN notification admin=%s: %s", admin_id, exc)
    except Exception as exc:
        logger.warning("Trial VPN notification failed: %s", exc)
    return web.json_response({'ok': True, 'event': 'trial_issued'})


def _verify_telegram_webapp_init_data(init_data: str) -> dict[str, Any] | None:
    """Validate Telegram Web App initData using the configured bot token."""
    if not init_data or len(init_data) > 8192:
        return None
    try:
        from config import BOT_TOKEN
        bot_token = str(BOT_TOKEN or '').strip()
    except Exception:
        bot_token = ''
    if not bot_token:
        return None
    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = (parsed.get('hash') or [''])[0]
    auth_date_raw = (parsed.get('auth_date') or [''])[0]
    if not received_hash or not auth_date_raw:
        return None
    try:
        auth_date = int(auth_date_raw)
    except ValueError:
        return None
    if auth_date <= 0 or abs(int(time.time()) - auth_date) > 86400:
        return None
    pairs = []
    for key in sorted(parsed):
        if key != 'hash':
            pairs.append(f"{key}={(parsed[key] or [''])[0]}")
    data_check_string = '\n'.join(pairs)
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        return None
    raw_user = (parsed.get('user') or [''])[0]
    try:
        user = json.loads(raw_user)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(user, dict):
        return None
    telegram_id = user.get('id')
    if isinstance(telegram_id, bool) or not isinstance(telegram_id, int) or telegram_id <= 0:
        return None
    return user


async def _trial_vpn_claim_handler(request: web.Request) -> web.Response:
    """Claim the native XFI CONNECT trial from a Telegram Web App."""
    secret = os.getenv(TRIAL_WEBHOOK_SECRET_ENV, '').strip()
    if not secret:
        return web.json_response({'ok': False, 'reason': 'not_configured'}, status=503)
    provided = request.headers.get('X-XFI-Webhook-Secret', '')
    if not hmac.compare_digest(provided, secret):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({'ok': False, 'reason': 'invalid_json'}, status=400)
    user = _verify_telegram_webapp_init_data(str(payload.get('initData') or ''))
    if not user:
        return web.json_response({'ok': False, 'reason': 'invalid_telegram_auth'}, status=401)
    from bot.services.trial_claim import activate_native_trial
    result = await activate_native_trial(
        int(user['id']),
        username=user.get('username'),
        first_name=user.get('first_name'),
        last_name=user.get('last_name'),
        bot=request.app[BOT_APP_KEY],
    )
    status = 200 if result.get('ok') else 409 if result.get('reason') == 'trial_already_used' else 400
    return web.json_response(result, status=status)


async def _payment_webhook_handler(request: web.Request) -> web.Response:
    provider_id = str(request.match_info.get('provider_id') or '')
    from bot.utils.payment_provider_registry import (
        get_payment_provider,
        validate_payment_webhook_secret,
    )
    try:
        provider = get_payment_provider(provider_id)
    except ValueError:
        provider = None
    if provider is None or provider.webhook_handler is None:
        return web.json_response({'ok': False, 'reason': 'provider_not_found'}, status=404)
    provided_secret = request.headers.get(WEBHOOK_SECRET_HEADER) or request.query.get('secret')
    if not validate_payment_webhook_secret(provider.provider_id, provided_secret):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    try:
        request_context = await _build_request_context(request, provider.provider_id)
        from bot.services.custom_payments import process_custom_payment_webhook
        result = await process_custom_payment_webhook(provider.provider_id, request_context, bot=request.app.get(BOT_APP_KEY))
    except Exception as e:
        logger.warning("Ошибка обработки webhook custom payment provider=%s: %s", provider_id, e)
        return web.json_response({'ok': False, 'reason': 'internal_error'}, status=500)
    return web.json_response(_public_webhook_response(result), status=_webhook_http_status(result))


async def _build_request_context(request: web.Request, provider_id: str) -> dict[str, Any]:
    body = await request.read()
    body_text = body.decode('utf-8', errors='replace')
    content_type = (request.content_type or '').casefold()
    json_payload = None
    form_payload: dict[str, Any] = {}
    if content_type == 'application/json' and body_text:
        with contextlib.suppress(json.JSONDecodeError):
            json_payload = json.loads(body_text)
    elif content_type == 'application/x-www-form-urlencoded' and body_text:
        parsed = parse_qs(body_text, keep_blank_values=True)
        form_payload = {key: values[0] if len(values) == 1 else values for key, values in parsed.items()}
    return {
        'provider_id': provider_id,
        'method': request.method,
        'path': request.path,
        'query': dict(request.query),
        'headers': dict(request.headers),
        'body': body_text,
        'body_bytes': body,
        'json': json_payload,
        'form': form_payload,
        'remote': request.remote,
        'content_type': request.content_type,
    }


def _public_webhook_response(result: dict[str, Any]) -> dict[str, Any]:
    response = {
        'ok': bool(result.get('ok')),
        'status': result.get('status'),
        'ignored': bool(result.get('ignored')),
        'completed': bool(result.get('completed')),
        'processed_now': bool(result.get('processed_now')),
    }
    if result.get('order_id'):
        response['order_id'] = result.get('order_id')
    if result.get('reason'):
        response['reason'] = result.get('reason')
    return response


def _webhook_http_status(result: dict[str, Any]) -> int:
    try:
        status = int(result.get('http_status') or (200 if result.get('ok') else 400))
    except (TypeError, ValueError):
        status = 400
    return status if 200 <= status <= 599 else 400


def _normalize_path_prefix(value: object) -> str:
    path = str(value or '').strip() or DEFAULT_WEBHOOKS_PATH_PREFIX
    if not path.startswith('/'):
        path = f'/{path}'
    path = path.rstrip('/') or '/'
    return DEFAULT_WEBHOOKS_PATH_PREFIX if path == '/' else path


__all__ = [
    'DEFAULT_WEBHOOKS_HOST', 'DEFAULT_WEBHOOKS_PATH_PREFIX', 'DEFAULT_WEBHOOKS_PORT',
    'WEBHOOKS_ENABLED_SETTING', 'WEBHOOKS_HOST_SETTING', 'WEBHOOKS_PATH_PREFIX_SETTING',
    'WEBHOOKS_PORT_SETTING', 'WEBHOOK_SECRET_HEADER', 'BOT_APP_KEY', 'CustomPaymentWebhookServer',
    'create_custom_payment_webhook_app', 'get_custom_payment_webhook_host',
    'get_custom_payment_webhook_path_prefix', 'get_custom_payment_webhook_port',
    'is_custom_payment_webhook_server_enabled', 'start_custom_payment_webhook_server',
]
