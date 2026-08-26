# local-https-mkcert

**Issue:** Local development over HTTP causes issues with HTTPS-only browser features
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Service workers, secure cookies, and some OAuth flows require HTTPS even locally.

## Pattern / Solution
mkcert -install adds local CA to system trust store. mkcert localhost 127.0.0.1 generates cert and key. Configure dev server to use the cert. Works with webpack, vite, next.js via --https flag with custom cert path.

## Gotchas
- CA must be installed on every machine/browser separately
- Chrome DevTools Security tab shows if cert is trusted — yellow shield means issue

## Related
- ngrok-local-tunneling, cloudflare-tunnel-dev, docker-compose-dev
