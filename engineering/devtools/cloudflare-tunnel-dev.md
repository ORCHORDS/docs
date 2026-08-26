# cloudflare-tunnel-dev

**Issue:** Need persistent tunnel URL without ngrok subscription
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ngrok free tier gives random URLs that reset; need a stable public URL for dev.

## Pattern / Solution
cloudflared tunnel --url http://localhost:3000 creates temporary tunnel (free). For persistent: create tunnel via Cloudflare dashboard, run cloudflared tunnel run. Requires Cloudflare account and domain. HTTPS by default.

## Gotchas
- Named tunnels require domain on Cloudflare and DNS CNAME record
- cloudflared must run continuously — use systemd or launchd service for persistence

## Related
- ngrok-local-tunneling, local-https-mkcert
