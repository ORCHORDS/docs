# cors-preflight-missing-headers

**Issue:** CORS preflight OPTIONS request succeeds but actual request fails due to missing `Access-Control-Allow-Headers`
**Date:** 2026-08-11
**Status:** documented

## Symptom
Browser throws `CORS policy: Request header field x-custom-header is not allowed` even though the preflight returns 200. Actual `GET`/`POST` request never reaches the handler.

## Root cause
The server returns `Access-Control-Allow-Origin` on the preflight response but omits `Access-Control-Allow-Headers`. Any custom header (`Authorization`, `Content-Type: application/json`, `X-*`) must be explicitly listed; the browser will block the real request if they are missing from the preflight response.

## Fix
```ts
// Cloudflare Worker example
if (request.method === 'OPTIONS') {
  return new Response(null, {
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Request-ID',
      'Access-Control-Max-Age': '86400',
    },
  });
}
```

## Detection
```
grep -r "Allow-Origin" src/ | grep -v "Allow-Headers"
```
Also: open DevTools → Network → find the OPTIONS request → inspect response headers for `Access-Control-Allow-Headers`.

## Related
- `wrangler-dev-vs-prod-bindings.md`
- `headers-case-insensitive-but-set-sensitive.md`
