# cors-pages-functions

**Issue:** ACAO on Pages Functions — explicit headers required
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy a Pages Function. The browser console shows:
```
Access to fetch at 'https://your-app.pages.dev/api/...' from
origin 'https://your-app.com' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present on the
requested resource.
```

The endpoint returns 200 with a JSON body, but the browser
refuses to read it. The fetch fails.

## Root cause
When the CF runtime detects **no function bundled for a path**,
it adds `Access-Control-Allow-Origin: *` automatically. But
when a function IS bundled, the runtime does NOT add CORS
headers. Your function must add them explicitly.

**Source:** Cloudflare Pages Functions + CORS:
https://developers.cloudflare.com/pages/functions/api-reference/

> "If your Function returns a Response with CORS headers, those
> headers will be preserved. ... If no Function exists for a
> given route, the static asset is served with default CORS
> headers."

## Fix
Add explicit CORS headers to every Pages Function:

```ts
export const onRequest: PagesFunction = async (context) => {
  const { request, env } = context;
  const origin = request.headers.get('Origin') ?? '*';

  // Handle preflight
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-CSRF-Token, Idempotency-Key',
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Max-Age': '86400',  // 24h
      },
    });
  }

  // Process the request
  const response = await handleRequest(request, env);

  // Add CORS headers to the response
  const headers = new Headers(response.headers);
  headers.set('Access-Control-Allow-Origin', origin);
  headers.set('Vary', 'Origin');  // important for cache
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
};
```

### Origin allowlist (not `*`)

For authenticated APIs, use an allowlist (not `*`):

```ts
const ALLOWED_ORIGINS = new Set([
  'https://your-app.com',
  'https://staging.your-app.com',
  'http://localhost:3000',  // dev
]);

const origin = request.headers.get('Origin') ?? '';
const allowOrigin = ALLOWED_ORIGINS.has(origin) ? origin : 'null';
```

`Access-Control-Allow-Origin: null` is the safe default (denies
all real origins; allows same-origin).

### Credentials

If you use cookies (`mc_sid`, etc.), the `Access-Control-Allow-
Credentials` header MUST be `true`. AND `Access-Control-Allow-
Origin` MUST NOT be `*` (browsers reject this combo).

### `Vary: Origin`

If the response differs by origin (e.g. different CORS headers
per origin), set `Vary: Origin` so caches don't serve the wrong
CORS headers to a different origin.

## Verification
- **Test:** `test/cors.test.ts > 5 endpoints return correct CORS
  headers` — passes
- **Live:** Browser DevTools Network tab shows the CORS headers
  on the response
- **OWASP ZAP scan:** No CORS misconfiguration findings

## Gotchas
- **`Access-Control-Allow-Origin: *` is rejected with cookies.**
  Browsers refuse the combination. Use a specific origin or
  omit credentials.
- **Preflight (`OPTIONS`) is separate from the actual request.**
  The browser sends OPTIONS first, expects 204, then sends the
  real request. Your function must handle OPTIONS.
- **The preflight cache** (`Access-Control-Max-Age: 86400`)
  controls how often the browser re-sends the preflight. 24h
  is the safe default; longer for less-changing APIs.
- **CORS is enforced by the browser, not the server.** Server-
  to-server requests (e.g. from another service) don't enforce
  CORS. CORS protects the user, not the API.
- **Don't put CORS in middleware for SPA + API in different
  origins.** Different paths, different needs. Use a Pages
  Function for the API and the SPA for the frontend.

## Related
- `pages-functions-exact-match-routing.md`
- `csrf-protection-double-submit.md` (companion for cookie auth)
- MDN CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
