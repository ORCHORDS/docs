# Mobile Safari ITP Cookie Partitioning

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Sessions established via Cloudflare Workers (cookie-based auth) are lost after navigating away from
the app in Mobile Safari, or are silently blocked in embedded WKWebView contexts. Third-party cookies
set by a Worker subdomain (`api.example.com`) are not forwarded to the main-frame origin
(`app.example.com`). Turnstile widget tokens appear to arrive but the downstream cookie Set by the
Worker is then partitioned and inaccessible.

## Context

Apple's Intelligent Tracking Prevention (ITP) 2.x partitions cookies and storage by "effective
top-level domain + 1" (eTLD+1). In the example project stack, the Capacitor shell and PWA share a KV-backed
session cookie scheme. When iOS treats the Worker origin as a third-party relative to the WebView
top-frame origin, that cookie lives in a separate partition and is never sent on subsequent requests.

CHIPS (Cookies Having Independent Partitioned State) is the W3C/Chrome proposal now also landing in
Safari TP. The `Partitioned` attribute explicitly opts a cookie into partition-scoped storage so the
browser doesn't silently quarantine it.

## ITP Version Behaviour Matrix

```
+-------------+---------------------+------------------------------------------+
| ITP Version | Safari Release      | Behaviour                                |
+-------------+---------------------+------------------------------------------+
| 2.0         | Safari 12           | 3rd-party cookies blocked after 24 h     |
| 2.1         | Safari 12.1         | JS-set cookies capped at 7 days          |
| 2.2         | Safari 13           | Script-writable storage capped at 1 day  |
|             |                     | if link-decoration detected              |
| 2.3         | Safari 14           | localStorage partitioned cross-site      |
| 3.x (CHIPS) | Safari TP / iOS 18+ | Partitioned attribute honoured           |
+-------------+---------------------+------------------------------------------+
```

## SameSite=None Secure Cookie Setup on the Worker

Cloudflare Workers must set session cookies with the full attribute string to survive ITP:

```typescript
// worker/src/auth/session.ts
export function buildSessionCookie(
  token: string,
  opts: { partitioned?: boolean } = {}
): string {
  const base = [
    `example project_session=${token}`,
    "HttpOnly",
    "Secure",
    "SameSite=None",
    "Path=/",
    `Max-Age=${60 * 60 * 24 * 7}`, // 7 days, ITP 2.1 cap
  ];
  if (opts.partitioned) {
    // CHIPS — Safari TP 18+ and Chrome 114+
    base.push("Partitioned");
  }
  return base.join("; ");
}

export async function handleLogin(request: Request, env: Env): Promise<Response> {
  const token = await mintSessionToken(env);
  const supportsChips = request.headers.get("Sec-CH-Partitioned-Cookies") === "1";
  return new Response(JSON.stringify({ ok: true }), {
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie": buildSessionCookie(token, { partitioned: supportsChips }),
    },
  });
}
```

## KV Session Fallback for Partitioned Environments

When cookies are unavailable (detected via a probe request), fall back to a short-lived KV token
passed as a Bearer header:

```typescript
// worker/src/auth/kv-session-fallback.ts
const KV_SESSION_TTL_SECONDS = 900; // 15 min — aggressive for anonymous social

export async function issueKvToken(env: Env, userId: string): Promise<string> {
  const token = crypto.randomUUID();
  await env.SESSION_KV.put(`kv:${token}`, userId, {
    expirationTtl: KV_SESSION_TTL_SECONDS,
  });
  return token;
}

export async function resolveKvToken(
  env: Env,
  authHeader: string | null
): Promise<string | null> {
  if (!authHeader?.startsWith("Bearer kv_")) return null;
  const token = authHeader.slice(7);
  return env.SESSION_KV.get(`kv:${token}`);
}
```

Client-side probe (React Native / Capacitor):

```typescript
// src/lib/session-probe.ts
export async function cookiesSupported(): Promise<boolean> {
  try {
    const r = await fetch("https://api.example.com/auth/cookie-probe", {
      credentials: "include",
    });
    const { echo } = await r.json();
    return echo === true;
  } catch {
    return false;
  }
}
```

## CHIPS Partitioned Attribute Detection

```typescript
// worker/src/middleware/chips-detect.ts
export function chipsSupported(request: Request): boolean {
  // Chrome sends Sec-CH-Partitioned-Cookies: 1
  // Safari TP sends Partitioned-Cookies: ?1 (structured field)
  const ch = request.headers.get("Sec-CH-Partitioned-Cookies");
  const sf = request.headers.get("Partitioned-Cookies");
  return ch === "1" || sf === "?1";
}
```

## Storage Partitioning vs Cookie Partitioning

```
+-----------------------+-----------------------------+------------------------------+
| Storage type          | ITP 2.x behaviour           | CHIPS / workaround           |
+-----------------------+-----------------------------+------------------------------+
| document.cookie       | 7-day cap (script-set)      | Partitioned attribute        |
| localStorage          | Partitioned by eTLD+1       | Use same-origin KV token     |
| sessionStorage        | Cleared on navigation       | In-memory store + re-auth    |
| IndexedDB             | 7-day ITP purge if no UX    | Service Worker keep-alive    |
| Cache Storage (PWA)   | Cleared with ITP purge      | Capacitor native storage     |
| WKWebView HTTPCookieStore | Shared with Safari      | Inject via WKUserScript      |
+-----------------------+-----------------------------+------------------------------+
```

## WKWebView Cookie Injection (Capacitor / iOS)

In Capacitor, inject the session cookie into WKWebView before navigating to prevent the
cross-origin partition from forming:

```swift
// ios/App/AppDelegate.swift
import WebKit

func injectSessionCookie(webView: WKWebView, token: String) {
    let cookie = HTTPCookie(properties: [
        .name: "example project_session",
        .value: token,
        .domain: ".example.com",
        .path: "/",
        .secure: "TRUE",
        .sameSitePolicy: "None",
    ])!
    webView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie)
}
```

## Anti-patterns

- Setting cookies with `SameSite=Lax` on Worker responses assumed to be used cross-origin — they
  will be stripped on cross-site sub-resource requests.
- Storing the session token in `localStorage` on the Worker subdomain and reading it from a
  different origin's JS — ITP partitions localStorage by eTLD+1.
- Relying on `document.cookie` with a domain attribute of `.example.com` from inside a WKWebView
  sub-frame — the cookie is silently partitioned under the sub-frame's eTLD+1.
- Setting `Max-Age` longer than 7 days for script-set cookies — ITP 2.1 caps them regardless.
- Issuing a `Partitioned` cookie without also sending `SameSite=None; Secure` — the attribute is
  ignored without the full pair.

## Gotchas

- `SameSite=None` without `Secure` causes the cookie to be rejected by all modern browsers.
- The `Partitioned` attribute is still behind a flag in some Safari versions; always implement the
  KV fallback.
- iOS WKWebView and Mobile Safari do NOT share the same cookie store by default before iOS 17;
  WKHTTPCookieStore injection is required.
- ITP purge timer resets only with direct user interaction with the domain — background Workers
  pings do NOT count.
- Cloudflare's `Cache-Control: private` on auth endpoints is required to prevent CDN caching of
  Set-Cookie headers leaking between users.

## Verification

```bash
# Confirm Set-Cookie attributes from Worker
curl -si https://api.example.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"anonId":"test"}' | grep -i set-cookie

# Expected output contains:
# SameSite=None; Secure; Partitioned  (on CHIPS-capable clients)
# OR
# SameSite=None; Secure              (on older clients, with KV fallback active)

# ITP behaviour check — use Safari Web Inspector:
# Storage > Cookies > filter by example.com
# "Partitioned" column should show "Yes" for cross-site contexts
```

## Related

- `ios-wkwebview-cloudflare-cookies.md`
- `mobile-auth-oauth-pkce.md`
- `pwa-stale-assets-cloudflare-pages-ios-safari.md`
- `capacitor-cloudflare-turnstile-integration.md`
- `browser-storage-quota-eviction-ios-safari.md`

## Sources

- https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
- https://developers.cloudflare.com/workers/runtime-apis/response/#set-cookie
- https://developers.cloudflare.com/kv/
- https://www.ietf.org/archive/id/draft-ietf-httpbis-rfc6265bis-15.txt (CHIPS)
- https://developer.apple.com/documentation/webkit/wkhttpcookiestore
