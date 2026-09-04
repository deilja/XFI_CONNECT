# XFI CONNECT Web Cabinet v2

Web cabinet for the existing XFI_CONNECT project. The web layer provides email-code authentication, cabinet, native tariff discovery, trial provisioning through 3X-UI, Platega payment creation/webhook, and Telegram linking.

## Architecture

- `XFI_CONNECT` remains the native source of truth for tariffs and Telegram-linked account data.
- Web-only session/payment/subscription state is stored in `WEB_DB_PATH`.
- 3X-UI is accessed with a Bearer API token; no panel password is embedded in source.
- Telegram confirmation requires `XFI_WEB_SECRET` in the `X-XFI-Secret` header.
- Authentication codes are printed to the application log until SMTP is connected.

## Run

```bash
cd web_cabinet_v2
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill SECRET_KEY, XUI_*, XFI_WEB_SECRET and PLATEGA_*
uvicorn app.main:app --host 127.0.0.1 --port 8090
```

For production, put nginx/Caddy in front of the app and keep the app bound to `127.0.0.1`.

## Main endpoints

- `GET /health`
- `GET /api/native/health`
- `GET /api/native/account/{telegram_id}`
- `POST /api/auth/request-code`
- `POST /api/auth/verify-code`
- `GET /api/auth/me`
- `GET /api/cabinet/tariffs`
- `GET /api/cabinet/subscriptions`
- `GET /api/cabinet/active`
- `POST /api/payments/create`
- `POST /api/payments/webhook`
- `POST /api/telegram/link`
- `POST /api/telegram/confirm`
- `DELETE /api/telegram/unlink`
- `POST /api/trial/claim`

## Important deployment notes

1. Generate strong random values for `SECRET_KEY` and `XFI_WEB_SECRET`.
2. Set `XUI_INBOUND_ID` to the inbound where web-issued clients must be created.
3. Set `XUI_SUB_BASE_URL` only if the corresponding 3X-UI subscription URL is exposed through the deployment.
4. Configure the Platega webhook URL as `/api/payments/webhook` and use the provider's callback/status payload.
5. Connect SMTP before enabling real users if login codes must be delivered by email.
6. The payment webhook records payment state. A production billing worker should perform idempotent tariff activation and native key synchronization before considering a payment fully fulfilled.

The current implementation deliberately does not connect XFI Guard.
