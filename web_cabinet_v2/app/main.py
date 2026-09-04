from __future__ import annotations

import hashlib
import html
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.api.native import router as native_router

APP = "XFI CONNECT"
ROOT = Path(__file__).resolve().parents[2]
WEB_DB = Path(os.getenv("WEB_DB_PATH", str(ROOT / "data" / "web_cabinet.db")))
SECRET = os.getenv("SECRET_KEY", "change-me")
COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
CODE_TTL = int(os.getenv("AUTH_CODE_TTL", "600"))
XUI_TIMEOUT = float(os.getenv("XUI_TIMEOUT", "20"))
XUI_VERIFY_TLS = os.getenv("XUI_VERIFY_TLS", "true").lower() == "true"
XUI_BASE_URL = os.getenv("XUI_BASE_URL", "").rstrip("/")
XUI_API_TOKEN = os.getenv("XUI_API_TOKEN", "")
XUI_INBOUND_ID = os.getenv("XUI_INBOUND_ID", "")
SUB_BASE_URL = os.getenv("XUI_SUB_BASE_URL", "").rstrip("/")
PLATEGA_BASE = os.getenv("PLATEGA_BASE_URL", "https://app.platega.io").rstrip("/")
PLATEGA_MERCHANT = os.getenv("PLATEGA_MERCHANT_ID", "")
PLATEGA_SECRET = os.getenv("PLATEGA_SECRET", "")
PLATEGA_RETURN = os.getenv("PLATEGA_RETURN_URL", "")

serializer = URLSafeTimedSerializer(SECRET, salt="xfi-connect-web-v2")
app = FastAPI(title="XFI CONNECT Web Cabinet v2", version="2.1.0")
app.include_router(native_router)


def db() -> sqlite3.Connection:
    WEB_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(WEB_DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT,
      telegram_id INTEGER, telegram_username TEXT, created_at TEXT NOT NULL,
      balance REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active'
    );
    CREATE TABLE IF NOT EXISTS auth_codes(
      id INTEGER PRIMARY KEY, email TEXT NOT NULL, code TEXT NOT NULL,
      expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS subscriptions(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, tariff_id INTEGER,
      status TEXT NOT NULL, expire_at TEXT, subscription_url TEXT,
      client_uuid TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS payments(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, tariff_id INTEGER,
      amount REAL NOT NULL, status TEXT NOT NULL, provider TEXT NOT NULL,
      external_id TEXT UNIQUE, payment_url TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS telegram_links(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, code TEXT UNIQUE NOT NULL,
      expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0
    );
    """)
    c.commit()
    return c


def now() -> datetime:
    return datetime.now(timezone.utc)


def token(uid: int) -> str:
    return serializer.dumps({"uid": uid})


def current_user(request: Request):
    raw = request.cookies.get("xfi_session")
    if not raw:
        return None
    try:
        data = serializer.loads(raw, max_age=30 * 24 * 3600)
    except (BadSignature, SignatureExpired):
        return None
    c = db()
    row = c.execute("SELECT * FROM users WHERE id=? AND status='active'", (int(data["uid"]),)).fetchone()
    c.close()
    return row


def require_user(request: Request):
    u = current_user(request)
    if not u:
        raise ValueError("AUTH")
    return u


def json_user(u):
    return {"id": u["id"], "email": u["email"], "telegram_id": u["telegram_id"],
            "telegram_username": u["telegram_username"], "balance": u["balance"], "status": u["status"]}


def native_tariffs() -> list[dict[str, Any]]:
    try:
        from app.services import xfi_native
        return xfi_native.get_tariffs() if xfi_native.enabled() else []
    except Exception:
        return []


def tariffs() -> list[dict[str, Any]]:
    out = []
    for t in native_tariffs():
        minor = int(t.get("price_minor") or 0)
        out.append({"id": int(t["id"]), "name": str(t.get("name") or "Тариф"),
                    "price": minor / 100 if minor else float(t.get("price_rub") or 0),
                    "duration_days": int(t.get("duration_days") or 30),
                    "traffic_gb": int(t.get("traffic_limit_gb") or 0) or None,
                    "device_limit": int(t.get("max_ips") or 1), "active": bool(t.get("is_active", 1))})
    if out:
        return [x for x in out if x["active"]]
    return [{"id": 1, "name": "1 месяц", "price": 299, "duration_days": 30, "traffic_gb": None, "device_limit": 2, "active": True}]


def send_code(email: str, code: str) -> None:
    # Production mail transport can be connected without changing the API contract.
    print(f"[XFI_CONNECT] AUTH CODE for {email}: {code}")


async def xui_add_client(client_uuid: str, email: str, expire_ms: int, total_gb: int | None):
    if not XUI_BASE_URL or not XUI_API_TOKEN or not XUI_INBOUND_ID:
        return {"ok": False, "reason": "3X-UI is not configured"}
    payload = {"id": int(XUI_INBOUND_ID), "settings": json.dumps({"clients": [{
        "id": client_uuid, "email": email, "enable": True, "expiryTime": expire_ms,
        "totalGB": int(total_gb or 0), "limitIp": 0
    }]})}
    headers = {"Authorization": f"Bearer {XUI_API_TOKEN}"}
    async with httpx.AsyncClient(timeout=XUI_TIMEOUT, verify=XUI_VERIFY_TLS) as client:
        r = await client.post(f"{XUI_BASE_URL}/panel/api/inbounds/addClient", json=payload, headers=headers)
        if r.status_code >= 400:
            return {"ok": False, "reason": f"3X-UI HTTP {r.status_code}", "body": r.text[:500]}
        try:
            data = r.json()
        except Exception:
            data = {}
        return {"ok": bool(data.get("success", True)), "data": data}


def subscription_url(sub_id: str) -> str | None:
    return f"{SUB_BASE_URL}/{sub_id}" if SUB_BASE_URL and sub_id else None


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    u = current_user(request)
    if u:
        return RedirectResponse("/cabinet", 302)
    return HTMLResponse(PAGE_HOME)


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(PAGE_LOGIN)


@app.get("/cabinet", response_class=HTMLResponse)
def cabinet_page(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", 302)
    return HTMLResponse(PAGE_CABINET)


@app.get("/health")
def health():
    return {"ok": True, "service": "xfi-connect-web-cabinet", "version": "2.1.0"}


@app.post("/api/auth/request-code")
async def request_code(request: Request):
    data = await request.json()
    email = str(data.get("email", "")).strip().lower()
    if "@" not in email or len(email) > 254:
        return JSONResponse({"detail": "Некорректный email"}, 400)
    c = db(); cutoff = (now() - timedelta(minutes=10)).isoformat()
    n = c.execute("SELECT COUNT(*) FROM auth_codes WHERE email=? AND created_at>?", (email, cutoff)).fetchone()[0]
    if n >= 5:
        c.close(); return JSONResponse({"detail": "Слишком много запросов"}, 429)
    code = f"{secrets.randbelow(1000000):06d}"
    c.execute("INSERT INTO auth_codes(email,code,expires_at,created_at) VALUES(?,?,?,?)",
              (email, code, (now() + timedelta(seconds=CODE_TTL)).isoformat(), now().isoformat()))
    c.commit(); c.close(); send_code(email, code)
    return {"message": "Код отправлен на почту"}


@app.post("/api/auth/verify-code")
async def verify_code(request: Request, response: Response):
    data = await request.json(); email = str(data.get("email", "")).strip().lower(); code = str(data.get("code", "")).strip()
    c = db(); row = c.execute("SELECT * FROM auth_codes WHERE email=? AND code=? AND used=0 ORDER BY id DESC LIMIT 1", (email, code)).fetchone()
    if not row or datetime.fromisoformat(row["expires_at"]) < now():
        c.close(); return JSONResponse({"detail": "Неверный или истёкший код"}, 400)
    c.execute("UPDATE auth_codes SET used=1 WHERE id=?", (row["id"],))
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u:
        c.execute("INSERT INTO users(email,created_at) VALUES(?,?)", (email, now().isoformat())); uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    else: uid = u["id"]
    c.commit(); c.close(); response.set_cookie("xfi_session", token(uid), httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=30*86400)
    return {"ok": True, "access_token": token(uid)}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("xfi_session"); return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    u = current_user(request)
    if not u: return JSONResponse({"detail": "Не авторизован"}, 401)
    return json_user(u)


@app.get("/api/cabinet/tariffs")
def get_tariffs():
    return tariffs()


@app.get("/api/cabinet/subscriptions")
def get_subscriptions(request: Request):
    u = current_user(request)
    if not u: return JSONResponse({"detail": "Не авторизован"}, 401)
    c = db(); rows = c.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC", (u["id"],)).fetchall(); c.close()
    return [dict(x) for x in rows]


@app.get("/api/cabinet/active")
def active(request: Request):
    u = current_user(request)
    if not u: return JSONResponse({"detail": "Не авторизован"}, 401)
    c = db(); r = c.execute("SELECT * FROM subscriptions WHERE user_id=? AND status='active' ORDER BY expire_at DESC LIMIT 1", (u["id"],)).fetchone(); c.close()
    if not r: return {"has_active": False, "subscription": None}
    if r["expire_at"] and datetime.fromisoformat(r["expire_at"]) <= now(): return {"has_active": False, "subscription": None}
    return {"has_active": True, "subscription": dict(r)}


@app.post("/api/payments/create")
async def create_payment(request: Request):
    u = current_user(request)
    if not u: return JSONResponse({"detail": "Не авторизован"}, 401)
    data = await request.json(); tid = int(data.get("tariff_id", 0)); t = next((x for x in tariffs() if x["id"] == tid), None)
    if not t: return JSONResponse({"detail": "Тариф не найден"}, 404)
    external = secrets.token_urlsafe(18)
    c = db(); c.execute("INSERT INTO payments(user_id,tariff_id,amount,status,provider,external_id,created_at) VALUES(?,?,?,?,?,?,?)",
                        (u["id"], tid, t["price"], "pending", "platega", external, now().isoformat())); pid = c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.commit(); c.close()
    if not PLATEGA_MERCHANT or not PLATEGA_SECRET:
        return {"payment_id": pid, "status": "pending", "payment_url": None, "message": "Platega не настроена"}
    headers = {"X-MerchantId": PLATEGA_MERCHANT, "X-Secret": PLATEGA_SECRET}
    body = {"paymentMethod": "SBP", "paymentDetails": {"amount": t["price"], "currency": "RUB"}, "description": f"{APP}: {t['name']}", "return": PLATEGA_RETURN, "payload": external}
    async with httpx.AsyncClient(timeout=XUI_TIMEOUT) as client:
        r = await client.post(f"{PLATEGA_BASE}/v2/transaction/process", headers=headers, json=body)
        if r.status_code >= 400: return JSONResponse({"detail": "Не удалось создать платёж", "provider": r.text[:300]}, 502)
        data = r.json()
    url = data.get("redirect") or data.get("paymentUrl") or data.get("url")
    c = db(); c.execute("UPDATE payments SET payment_url=? WHERE id=?", (url, pid)); c.commit(); c.close()
    return {"payment_id": pid, "status": "pending", "payment_url": url, "external_id": external}


@app.post("/api/payments/webhook")
async def payment_webhook(request: Request):
    data = await request.json(); status = str(data.get("status", "")).upper(); external = str(data.get("payload") or data.get("transactionId") or "")
    if status not in {"CONFIRMED", "CANCELED", "CHARGEBACKED"}: return {"ok": True}
    c = db(); p = c.execute("SELECT * FROM payments WHERE external_id=?", (external,)).fetchone()
    if not p: c.close(); return {"ok": True}
    c.execute("UPDATE payments SET status=? WHERE id=?", ("paid" if status == "CONFIRMED" else status.lower(), p["id"]))
    c.commit(); c.close(); return {"ok": True}


@app.post("/api/telegram/link")
def telegram_link(request: Request):
    u = current_user(request)
    if not u: return JSONResponse({"detail": "Не авторизован"}, 401)
    code = secrets.token_urlsafe(8); exp = now() + timedelta(minutes=15); c = db()
    c.execute("INSERT INTO telegram_links(user_id,code,expires_at) VALUES(?,?,?)", (u["id"], code, exp.isoformat())); c.commit(); c.close()
    bot = os.getenv("TELEGRAM_BOT_USERNAME", "XFI_VPN_bot")
    return {"code": code, "expires_at": exp.isoformat(), "bot_link": f"https://t.me/{bot}?start=web_{code}"}


@app.post("/api/telegram/confirm")
async def telegram_confirm(request: Request):
    secret = request.headers.get("X-XFI-Secret", "")
    if not secrets.compare_digest(secret, os.getenv("XFI_WEB_SECRET", "")):
        return JSONResponse({"detail": "Forbidden"}, 403)
    data = await request.json(); code = str(data.get("code", "")); tg = int(data.get("telegram_id"))
    c = db(); link = c.execute("SELECT * FROM telegram_links WHERE code=? AND used=0", (code,)).fetchone()
    if not link or datetime.fromisoformat(link["expires_at"]) < now(): c.close(); return JSONResponse({"detail": "Код недействителен"}, 400)
    c.execute("UPDATE telegram_links SET used=1 WHERE id=?", (link["id"],)); c.execute("UPDATE users SET telegram_id=?,telegram_username=? WHERE id=?", (tg, data.get("telegram_username"), link["user_id"])); c.commit(); c.close(); return {"ok": True}


@app.delete("/api/telegram/unlink")
def telegram_unlink(request: Request):
    u = current_user(request)
    if not u: return JSONResponse({"detail": "Не авторизован"}, 401)
    c = db(); c.execute("UPDATE users SET telegram_id=NULL,telegram_username=NULL WHERE id=?", (u["id"],)); c.commit(); c.close(); return {"ok": True}


@app.post("/api/trial/claim")
async def trial(request: Request):
    u = current_user(request)
    if not u: return JSONResponse({"detail": "Не авторизован"}, 401)
    c = db(); exists = c.execute("SELECT 1 FROM subscriptions WHERE user_id=? AND tariff_id=-1", (u["id"],)).fetchone()
    if exists: c.close(); return JSONResponse({"detail": "Пробный доступ уже использован"}, 409)
    client_uuid = str(uuid.uuid4()); exp = now() + timedelta(days=int(os.getenv("TRIAL_DAYS", "3"))); result = await xui_add_client(client_uuid, u["email"], int(exp.timestamp()*1000), int(os.getenv("TRIAL_TRAFFIC_GB", "0")))
    if not result["ok"]: c.close(); return JSONResponse({"detail": "3X-UI не настроена для выдачи доступа"}, 503)
    subid = client_uuid; url = subscription_url(subid); c.execute("INSERT INTO subscriptions(user_id,tariff_id,status,expire_at,subscription_url,client_uuid,created_at) VALUES(?,?,?,?,?,?,?)", (u["id"], -1, "active", exp.isoformat(), url, client_uuid, now().isoformat())); c.commit(); c.close()
    return {"ok": True, "message": "Пробная подписка активирована", "subscription_url": url, "expire_at": exp.isoformat()}


PAGE_HOME = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{APP}</title><style>{CSS}</style></head><body><main class="wrap hero"><div class="logo">XFI CONNECT</div><h1>VPN без лишнего</h1><p>Личный кабинет, тарифы, оплата и управление подпиской.</p><a class="btn" href="/login">Войти в кабинет</a></main></body></html>'''
PAGE_LOGIN = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Вход — {APP}</title><style>{CSS}</style></head><body><main class="wrap card"><h1>Вход</h1><p>Введите email. Код будет выведен в лог сервера до подключения SMTP.</p><input id="email" type="email" placeholder="you@example.com"><button class="btn" onclick="code()">Получить код</button><div id="verify" hidden><input id="otp" inputmode="numeric" maxlength="6" placeholder="Код"><button class="btn" onclick="login()">Войти</button></div><pre id="msg"></pre></main><script>async function code(){let email=document.getElementById('email').value;let r=await fetch('/api/auth/request-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});let d=await r.json();document.getElementById('msg').textContent=d.detail||d.message||'';if(r.ok)document.getElementById('verify').hidden=false}async function login(){let email=document.getElementById('email').value,code=document.getElementById('otp').value;let r=await fetch('/api/auth/verify-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,code})});let d=await r.json();if(r.ok)location='/cabinet';else document.getElementById('msg').textContent=d.detail}</script></body></html>'''
PAGE_CABINET = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Кабинет — {APP}</title><style>{CSS}</style></head><body><main class="wrap"><header><b>{APP}</b><button onclick="logout()">Выйти</button></header><section class="card"><h1>Личный кабинет</h1><div id="me"></div><h2>Подписка</h2><div id="active">Загрузка…</div></section><section class="card"><h2>Тарифы</h2><div id="tariffs"></div></section><section class="card"><h2>Telegram</h2><button class="btn" onclick="tg()">Получить код привязки</button><pre id="tgout"></pre></section></main><script>async function j(u,o){let r=await fetch(u,o);let d=await r.json();if(r.status==401)location='/login';return d}async function load(){let m=await j('/api/auth/me');document.getElementById('me').textContent=m.email;let a=await j('/api/cabinet/active');document.getElementById('active').innerHTML=a.has_active?`До: ${{new Date(a.subscription.expire_at).toLocaleString()}}<br><code>${{a.subscription.subscription_url||'Ссылка появится после настройки подписки'}}</code>`:'Активной подписки нет';let ts=await j('/api/cabinet/tariffs');document.getElementById('tariffs').innerHTML=ts.map(t=>`<div class="tariff"><b>${{t.name}}</b> — ${{t.price}} ₽ / ${{t.duration_days}} дн. <button onclick="pay(${{t.id}})">Оплатить</button></div>`).join('')}async function pay(id){let d=await j('/api/payments/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tariff_id:id})});if(d.payment_url)location=d.payment_url;else alert(d.message||d.detail||'Платёж не создан')}async function tg(){let d=await j('/api/telegram/link',{method:'POST'});document.getElementById('tgout').textContent=d.bot_link+'\\nКод: '+d.code}async function logout(){await fetch('/api/auth/logout',{method:'POST'});location='/'}load()</script></body></html>'''
CSS = '''*{box-sizing:border-box}body{margin:0;background:#080b12;color:#eef2f7;font:16px system-ui,sans-serif}.wrap{max-width:920px;margin:auto;padding:28px 18px}.hero{min-height:100vh;display:flex;flex-direction:column;justify-content:center;align-items:flex-start}.logo{font-weight:800;letter-spacing:.08em;color:#65a3ff}h1{font-size:42px;margin:12px 0}h2{margin-top:28px}p{color:#9aa6b2;line-height:1.6}.card{background:#111722;border:1px solid #263142;border-radius:18px;padding:24px;margin:18px 0}input{width:100%;padding:13px;border-radius:10px;border:1px solid #344052;background:#0b1018;color:#fff;margin:8px 0 12px}.btn,button{border:0;border-radius:10px;padding:11px 16px;background:#3478f6;color:#fff;cursor:pointer}.tariff{padding:15px 0;border-bottom:1px solid #263142}.tariff button{float:right}header{display:flex;justify-content:space-between;align-items:center}code,pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#a9d0ff}a{color:inherit;text-decoration:none}'''

@app.on_event("startup")
def startup():
    c = db(); c.close()
