# Trial VPN → XFI CONNECT

Trial VPN can notify the existing XFI CONNECT backend after a test subscription is issued. No second Telegram bot token is stored in Trial VPN.

## Endpoint

The existing webhook server exposes:

```text
POST /custom-payment-webhook/trial-vpn
```

The default local listener is `127.0.0.1:8088`. Put it behind nginx/HTTPS if Trial VPN is on another server.

## Secret

Set the same random secret on the XFI CONNECT service and Trial VPN:

```env
TRIAL_VPN_WEBHOOK_SECRET=<long-random-secret>
```

Trial VPN sends it as:

```text
X-XFI-Webhook-Secret: <long-random-secret>
```

## Trial VPN configuration

In `trial-vpn/server/.env`:

```env
XFI_CONNECT_WEBHOOK_URL=https://<xfi-domain>/custom-payment-webhook/trial-vpn
XFI_CONNECT_WEBHOOK_SECRET=<same-secret>
```

The event contains only operational data:

```json
{
  "type": "trial_issued",
  "email": "trial_...",
  "expiresAt": "2026-09-05T...Z",
  "hours": 1,
  "totalTrials": 1248
}
```

The subscription URL and client UUID are deliberately not sent to XFI CONNECT through this event.

## XFI CONNECT listener

The listener starts when either the existing custom payment webhook feature is enabled or `TRIAL_VPN_WEBHOOK_SECRET` is present in the XFI CONNECT service environment.

For an external Trial VPN server, configure nginx to proxy the HTTPS route to `127.0.0.1:8088`.

Example:

```nginx
location = /custom-payment-webhook/trial-vpn {
    proxy_pass http://127.0.0.1:8088/custom-payment-webhook/trial-vpn;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Test

After restarting XFI CONNECT:

```bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-XFI-Webhook-Secret: <same-secret>' \
  --data '{"type":"trial_issued","hours":1,"expiresAt":"2026-09-05T15:00:00Z","totalTrials":1248}' \
  https://<xfi-domain>/custom-payment-webhook/trial-vpn
```

Expected response:

```json
{"ok":true,"event":"trial_issued"}
```

The existing XFI CONNECT admin notification path is used for the event. A user-specific Telegram message is intentionally not attempted because a public Trial VPN page does not have a trusted Telegram chat identity.
