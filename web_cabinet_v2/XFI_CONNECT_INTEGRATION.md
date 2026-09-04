# XFI CONNECT Web Cabinet v2 — Native Integration

Web Cabinet v2 is designed as a native web layer for the existing XFI_CONNECT bot and database.

## Architecture

- XFI_CONNECT remains the source of truth for users, tariffs and VPN keys.
- Web Cabinet authenticates a Telegram-linked user and reads/writes through the native bridge.
- 3X-UI remains the VPN provisioning layer.
- Payment webhooks are idempotent: repeated callbacks must not create duplicate keys.
- Production provisioning must never use demo/fake key generation.

## Environment

`XFI_CONNECT_DB_PATH` — path to the existing `vpn_bot.db`.

`XFI_CONNECT_SERVER_ID` — optional default XFI_CONNECT server ID.

`XFI_AI_*` variables are intentionally not required by the cabinet.

## Native endpoints

- `GET /api/native/health`
- `GET /api/native/account`

The native bridge resolves the current Telegram-linked account and exposes native tariffs/keys without introducing a second business database.

## Deployment

Run behind nginx/Caddy and keep the native XFI_CONNECT database outside the web application's writable code directory. Use a dedicated service account with only the permissions required to read/write the database and reach the local 3X-UI API.
