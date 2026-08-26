# CORS in Cloudflare Workers: Preflight Caching, Mobile Behaviour, and Credentialed Requests

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Mobile app makes repeated OPTIONS preflight requests instead of using the cached preflight result,
causing visible latency spikes. Browser integration tests pass but native Android HTTP client
returns `ERR_FAILED` for credentialed API requests despite correct CORS headers. Wildcard
`Access-Control-Allow-Origin: *` blocks cookie-based authentication. Workers CORS middleware
accidentally reflects any `Origin` header, enabling CSRF via cross-origin fetch.

## Context

example project (example.com) serves an anonymous social platform API from Cloudflare Workers on
`api.example.com`. Web clients at `example.com` and native mobile apps (React Native) both call the
API. Mobile clients use `fetch()` inside a WebView or OkHttp/NSURLSession natively — these have
different preflight cache lifetimes, credentialed-request rules, and header exposure behaviour
compared to desktop browsers. Getting CORS wrong either breaks mobile clients or opens up CSRF
for web clients.

---

## CORS Middleware for Workers

A robust Workers CORS middleware validates the origin against an allow-list, never reflects
arbitrary origins, and adds preflight cache headers.

```ts
// workers/src/lib/cors.ts

const ALLOWED_ORIGINS = new Set([
  'https://example.com',
  'https://www.example.com',
  'https://staging.example.com',
]);

const ALLOWED_METHODS = 'GET, POST, PUT, DELETE, PATCH, OPTIONS';
const ALLOWED_HEADERS = 'Content-Type, Authorization, X-Request-ID, X-Nonce';
const EXPOSED_HEADERS = 'X-Request-ID, X-RateLimit-Remaining, X-RateLimit-Reset';
// Max browsers honour: Chrome 2h, Firefox 24h, Safari 5min — set to 2h
const PREFLIGHT_MAX_AGE = '7200';

export interface CorsOptions {
  allowCredentials?: boolean; // true for cookie/JWT flows
}

export function corsHeaders(origin: string | null, opts: CorsOptions = {}): HeadersInit {
  if (!origin || !ALLOWED_ORIGINS.has(origin)) {
    // No CORS headers — browser will block the cross-origin response
    return {};
  }

  const headers: Record<string, string> = {
    'Access-Control-Allow-Origin': origin,   // exact match, not wildcard
    'Access-Control-Allow-Methods': ALLOWED_METHODS,
    'Access-Control-Allow-Headers': ALLOWED_HEADERS,
    'Access-Control-Expose-Headers': EXPOSED_HEADERS,
    'Access-Control-Max-Age': PREFLIGHT_MAX_AGE,
    Vary: 'Origin',                          // required for CDN correctness
  };

  if (opts.allowCredentials) {
    // Wildcard is FORBIDDEN when credentials are used
    headers['Access-Control-Allow-Credentials'] = 'true';
  }

  return headers;
}

export function handlePreflight(request: Request, opts: CorsOptions = {}): Response | null {
  if (request.method !== 'OPTIONS') return null;

  const origin = request.headers.get('Origin');
  const headers = corsHeaders(origin, opts);

  // No CORS headers added for unknown origins — return 204 without them
  return new Response(null, { status: 204, headers });
}

// Attach CORS headers to any response
export function withCors(response: Response, request: Request, opts: CorsOptions = {}): Response {
  const origin = request.headers.get('Origin');
  const headers = corsHeaders(origin, opts);
  const mutable = new Response(response.body, response);
  for (const [k, v] of Object.entries(headers)) {
    mutable.headers.set(k, v);
  }
  return mutable;
}
```

---

## Preflight Caching: Browser vs Mobile

`Access-Control-Max-Age` tells browsers to cache preflight results and skip repeat OPTIONS
requests. The actual cache duration is capped per runtime:

| Runtime                             | Max-Age cap    | Cache scope         | Notes                                     |
|-------------------------------------|----------------|---------------------|-------------------------------------------|
| Chrome / Chromium (desktop + Android)| 7200 s (2 h)  | Per (origin, URL, headers) | Resets on navigation or cache clear |
| Firefox                             | 86400 s (24 h) | Per (origin, URL)   | Longest cache; mobile same               |
| Safari / WKWebView                  | 300 s (5 min)  | Per (origin, URL)   | Short cap; mobile apps see frequent OPTIONS|
| React Native `fetch()` (Hermes)     | Inherits WebView| Per session        | WebView controls cache                   |
| OkHttp (Android native)             | No preflight   | N/A                 | Sends headers directly — no OPTIONS      |
| NSURLSession (iOS native)           | No preflight   | N/A                 | Same; CORS is browser concept only       |
| Axios in React Native WebView       | 300 s (WKWebView)| Per session       | Matches WKWebView cap                    |

Key insight: native OkHttp and NSURLSession do not send preflight requests — CORS is a browser
security mechanism. Native HTTP clients do not enforce the Same-Origin Policy. Credentialed request
restrictions do not apply to native clients — they only apply to web contexts running JS.

---

## Credentialed Requests

When the web client uses `credentials: 'include'` (cookies or HTTP auth), the server must:
1. Return the exact request `Origin` (not `*`) in `Access-Control-Allow-Origin`.
2. Include `Access-Control-Allow-Credentials: true`.
3. Not use `*` in `Access-Control-Allow-Headers` or `Access-Control-Allow-Methods`.

```ts
// Web client — posting a new anonymous post with session cookie
const response = await fetch('https://api.example.com/posts', {
  method: 'POST',
  credentials: 'include',      // sends session cookie cross-origin
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ body: 'Hello world' }),
});
```

```ts
// Worker handler — credentialed CORS
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const preflight = handlePreflight(request, { allowCredentials: true });
    if (preflight) return preflight;

    const response = await routeRequest(request, env);
    return withCors(response, request, { allowCredentials: true });
  },
};
```

Returning `Access-Control-Allow-Origin: *` alongside `Access-Control-Allow-Credentials: true`
causes all browsers to reject the response — the combination is invalid per the Fetch spec.

---

## Mobile WebView CORS vs Native HTTP

```ts
// React Native — decide whether to use WebView fetch or native fetch
// WebView fetch: goes through WKWebView/WebView CORS enforcement
// Native fetch (via react-native fetch polyfill): no CORS enforcement

// For API calls from React Native, prefer native fetch — no CORS header needed
// For WebView-embedded pages calling the API, full CORS applies

// If the React Native app embeds a WebView that calls api.example.com:
const webviewConfig = {
  // Inject auth header to avoid credentialed CORS complexity in WebView
  injectedJavaScript: `
    const originalFetch = window.fetch;
    window.fetch = (url, opts = {}) => {
      if (url.startsWith('https://api.example.com')) {
        opts.headers = { ...opts.headers, Authorization: 'Bearer ${token}' };
        delete opts.credentials; // use token, not cookie
      }
      return originalFetch(url, opts);
    };
  `,
};
```

Prefer Bearer tokens over cookies for mobile → API communication. Cookies require credentialed
CORS; tokens work with simple `Authorization` headers and avoid `credentials: 'include'`.

---

## Common CORS Misconfigurations

| Misconfiguration                              | Risk                                        | Correct Pattern                                   |
|-----------------------------------------------|---------------------------------------------|---------------------------------------------------|
| Reflect any `Origin` header                   | CSRF via any origin                         | Validate against allow-list before reflecting     |
| `Allow-Origin: *` with credentials           | Browser rejects; if accepted, CSRF risk     | Exact origin + `Allow-Credentials: true`         |
| Missing `Vary: Origin`                        | CDN caches wrong-origin response             | Always add `Vary: Origin` when echoing origin    |
| Allow-list includes `null` origin             | Sandboxed iframes bypass                    | Never add `null` to allow-list                   |
| Overly broad `Allow-Headers: *`              | Exposes internal headers; forbidden w/ creds| Enumerate exact headers                           |
| Allowing `http://` origins in production      | Downgrade attack possible                   | Allow-list must be `https://` only               |
| No preflight handler → 404 on OPTIONS         | Mobile WebView retries loop                 | Handle OPTIONS before routing                    |

---

## Cloudflare Cache and CORS

Cloudflare edge caches responses. If a CORS response is cached without `Vary: Origin`, a request
from an allowed origin may receive a cached response that has the CORS headers for a different
(or no) origin.

```toml
# wrangler.toml — cache rules must respect Vary
[cache]
# Workers Cache API respects Vary automatically when you set it on the response header
# Ensure any Cloudflare Cache Rules for api.example.com include "Vary: Origin" in cache key
```

```ts
// workers/src/lib/cache.ts — cache API response with correct Vary
async function cacheResponse(
  cache: Cache,
  request: Request,
  response: Response,
): Promise<void> {
  // Only cache GET responses; include Origin in cache key via Vary header
  if (request.method !== 'GET') return;
  if (!response.headers.get('Vary')?.includes('Origin')) return; // safety check
  await cache.put(request, response.clone());
}
```

---

## Anti-patterns

- Using a regex like `/example project\.app/` to validate `Origin` — `evil-example.com` would match; use
  exact Set membership after parsing the URL.
- Setting `Access-Control-Max-Age` to `86400` on WKWebView builds — Safari caps at 300 s anyway;
  the large value wastes no time but can mislead developers who test only on Chrome.
- Adding `OPTIONS` to `Access-Control-Allow-Methods` — the OPTIONS method is used for preflight
  itself, not a declared cross-origin action; it is implicit and adding it is confusing.
- Returning CORS headers on error responses (401, 403, 500) from a different code path that omits
  the middleware — the browser blocks the error body, so the client gets no error detail.

## Gotchas

- Cloudflare Workers `fetch()` from within a Worker to D1 or KV does not go through the browser
  CORS path — CORS only applies to the *response from the Worker to the browser*.
- `Access-Control-Expose-Headers` is required for the client JS to read custom headers like
  `X-RateLimit-Remaining` even on same-origin-looking requests; without it, `response.headers.get()`
  returns null for those headers.
- React Native `fetch()` in the new architecture (JSI) uses the native HTTP stack — no CORS
  enforcement; but `XMLHttpRequest` in the old architecture goes through the JS CORS polyfill.
- Pre-flight requests must not require authentication — do not validate tokens on OPTIONS requests
  or mobile WebViews may silently fail to send the actual request.

## Verification

```bash
# 1. Preflight returns correct headers for allowed origin
curl -si -X OPTIONS https://api.example.com/posts \
  -H 'Origin: https://example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: Content-Type' \
  | grep -i 'access-control'
# Expect: Allow-Origin: https://example.com, Allow-Methods includes POST, Max-Age: 7200

# 2. Unknown origin gets no CORS headers
curl -si -X OPTIONS https://api.example.com/posts \
  -H 'Origin: https://evil.com' \
  -H 'Access-Control-Request-Method: POST' \
  | grep -i 'access-control'
# Expect: empty output

# 3. Credentialed request returns exact origin + credentials header
curl -si https://api.example.com/posts \
  -H 'Origin: https://example.com' \
  -H 'Cookie: session=test' \
  | grep -i 'access-control'
# Expect: Allow-Origin: https://example.com, Allow-Credentials: true

# 4. Vary header present
curl -si https://api.example.com/posts \
  -H 'Origin: https://example.com' \
  | grep -i '^vary'
# Expect: Vary: Origin
```

## Related

- `cors-security-misconfiguration.md`
- `cors-wildcard-with-credentials.md`
- `csrf-protection-double-submit.md`
- `csrf-vs-cors-vs-samesite.md`
- `oauth-pkce-mobile-cloudflare-workers.md`

## Sources

- Fetch Living Standard — CORS: https://fetch.spec.whatwg.org/#cors-protocol
- MDN CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
- Cloudflare Workers CORS guide: https://developers.cloudflare.com/workers/examples/cors-header-proxy/
- WKWebView CORS limits: https://webkit.org/blog/8517/release-notes-for-safari-technology-preview-68/
- OkHttp no preflight: https://square.github.io/okhttp/features/calls/
