# XFI CONNECT Web Cabinet v2

Native web layer for the existing XFI_CONNECT bot.

## Principle

XFI_CONNECT remains the source of truth. The cabinet reads the existing `vpn_bot.db`; it does not create a parallel user/tariff/key database.

## Run

```bash
cd web_cabinet_v2
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Set `XFI_CONNECT_DB_PATH` to the real XFI_CONNECT `database/vpn_bot.db`.

## API

`GET /health`

`GET /api/native/health`

`GET /api/native/account/{telegram_id}`

Production deployment should put the application behind nginx/Caddy and restrict database permissions.
