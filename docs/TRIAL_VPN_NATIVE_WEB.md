# Native Trial VPN from Web App

XFI CONNECT now exposes a local endpoint for the Trial VPN web frontend:

`POST /custom-payment-webhook/trial-vpn/claim`

The endpoint requires `X-XFI-Webhook-Secret` and a Telegram Web App `initData` payload. The server validates the Telegram signature with the existing XFI CONNECT bot token before using the authenticated Telegram user ID.

## Flow

1. User opens Trial VPN as a Telegram Web App.
2. Browser receives `Telegram.WebApp.initData`.
3. Trial VPN forwards only `initData` to the local XFI CONNECT endpoint.
4. XFI CONNECT verifies the Telegram signature and extracts the real user ID.
5. XFI CONNECT checks the existing native trial flag and configured trial tariff.
6. XFI CONNECT creates the normal trial order/key and provisions the VPN through its existing provisioning layer.
7. The native trial flag is consumed only after successful provisioning.
8. The subscription URL is returned to the web frontend for INCY import.

The web service does not receive or store the XFI CONNECT Bot Token and does not create independent 3X-UI trial clients.

## Endpoint example

```http
POST http://127.0.0.1:8088/custom-payment-webhook/trial-vpn/claim
X-XFI-Webhook-Secret: <shared-secret>
Content-Type: application/json

{"initData":"<Telegram.WebApp.initData>"}
```

A successful response contains `subscription`, `expires_at`, `key_id`, `order_id`, and `telegram_id`.

The endpoint is intended to remain bound to `127.0.0.1`; nginx should never expose port 8088 directly.
