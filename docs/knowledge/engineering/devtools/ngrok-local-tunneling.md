# ngrok-local-tunneling

**Issue:** Sharing local dev server with teammates or testing webhooks requires deployment
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Webhook from Stripe/GitHub needs to reach local server for development testing.

## Pattern / Solution
ngrok http 3000 creates public HTTPS tunnel to localhost:3000. Free tier provides random URL; paid provides stable subdomain. ngrok.yml for persistent config. Inspect traffic at localhost:4040.

## Gotchas
- Free tier URLs expire on restart — use environment-specific webhook URLs in config
- ngrok intercepts traffic — do not tunnel sensitive production-like data through free tier

## Related
- cloudflare-tunnel-dev, local-https-mkcert
