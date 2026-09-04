#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${XFI_WEB_DIR:-/opt/XFI_CONNECT/web_cabinet_v2}"
PORT="${XFI_WEB_PORT:-8090}"

if [[ $EUID -ne 0 ]]; then echo 'Run as root.' >&2; exit 1; fi
mkdir -p "$APP_DIR/data"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then cp "$APP_DIR/.env.example" "$APP_DIR/.env"; fi
chmod 600 "$APP_DIR/.env"

cat >/etc/systemd/system/xfi-connect-web.service <<EOF
[Unit]
Description=XFI CONNECT Web Cabinet
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$APP_DIR/data

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now xfi-connect-web.service
systemctl --no-pager --full status xfi-connect-web.service || true

echo
 echo "XFI CONNECT Web Cabinet installed on 127.0.0.1:$PORT"
 echo "Edit $APP_DIR/.env, then: systemctl restart xfi-connect-web"
