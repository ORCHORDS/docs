# ios-safari-cookie-itp-auth-cloudflare

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Anonymous session cookie disappears after seven days on iOS
Safari. Users reach `cdn.example.com` or `api.example.com` and
receive 401 responses even though they authenticated on
`example.com` minutes earlier. OAuth callbacks using
`response_mode=form_post` drop the session cookie entirely,
breaking CSRF-state validation on the redirect-back leg.

## Context

example project issues a session token to every visitor — no login,
no third-party cookies. The token must travel from the SPA
(`example.com`) to `api.example.com` and `cdn.example.com`. ITP
treats auth and tracker cookies identically; the fix is to
move from `document.cookie` to HTTP `Set-Cookie` from a Worker.

## ITP 2.x: 7-Day JavaScript Cookie Cap

Safari ITP 2.1 (April 2019) caps every `document.cookie` write
at 7 days of storage regardless of the `expires` or `max-age`
supplied by the script. ITP 2.2 (June 2019) collapsed that to
24 hours when the landing URL contained tracker parameters
(`fbclid`, `gclid`). Safari 17 / iOS 17 (2023) extended Link
Tracking Protection to Private Browsing and strips those
parameters outright.

```js
// Still capped at 7 days — ITP ignores the max-age value
document.cookie =
  'anon_sid=abc; max-age=31536000; path=/; Secure';
```

Safari 17+ also checks CNAME cloaking: if `api.example.com`
resolves to a different /24 subnet than `example.com`, the cap
applies regardless of cookie origin. Keep all subdomains
orange-clouded through Cloudflare anycast to satisfy this.

## HttpOnly Set-Cookie from a Worker Bypasses the JS Cap

A cookie delivered in a server `Set-Cookie` header from a
same-site origin is not subject to the 7-day cap. The Worker
on `api.example.com` creates the session on first visit and
refreshes `Max-Age` on every authenticated response.

```ts
// api.example.com Worker — POST /auth/anon
const sid = await createAnonSession(env);
return new Response(JSON.stringify({ ok: true }), {
  headers: {
    'Content-Type': 'application/json',
    // HttpOnly → JS-set-cookie cap never applies
    'Set-Cookie': [
      `__Secure-anon_sid=${sid}`, 'Path=/',
      'HttpOnly', 'Secure', 'SameSite=Lax',
      'Max-Age=7776000',   // 90 days
      'Domain=example.com', // shared across subdomains
    ].join('; '),
  },
});
```

`HttpOnly` means `document.cookie` cannot read or write the
cookie, so the ITP JS-cap rule never triggers. The Worker
must re-issue `Set-Cookie` to refresh `Max-Age` — touching
the cookie from JavaScript re-subjects it to the 7-day cap.

## SameSite=None, Secure, and the `__Secure-` Prefix

Rules enforced by all modern browsers:

1. `SameSite=None` **requires** `Secure`. A `None` cookie
   without `Secure` is silently dropped — no error is raised.
2. The `__Secure-` prefix requires `Secure` and HTTPS.
   Confirm "Always Use HTTPS" is enabled in zone settings.
3. `__Host-` additionally forbids `Domain=` and requires
   `Path=/`. Do not use it for subdomain-shared cookies.

Use `SameSite=Lax` for the example project session cookie.
`SameSite=None; Secure` is for explicit embed scenarios only.
Workers pass `__Secure-`/`__Host-` names through unchanged.

## SameSite=Lax Blocks POST OAuth Redirects

`SameSite=Lax` (browser default since Chrome 80 / Safari 13)
sends cookies on top-level GET navigations but blocks them on
cross-site POST. `response_mode=form_post` sends the auth code
via POST from the provider, so the session cookie is absent:

```
POST https://example.com/auth/callback
Origin: https://accounts.provider.com
Cookie: (blocked — cross-site POST, SameSite=Lax)
```

Without the session cookie the server cannot validate the CSRF
state parameter and rejects the callback.

Fixes:
- Prefer `response_mode=query` (GET redirect) — Lax permits
  cookies on top-level GETs.
- Use PKCE with verifier in `sessionStorage`; validate server-
  side after the GET redirect, no cookie needed on POST path.
- As a last resort, issue a short-lived `SameSite=None; Secure`
  cookie scoped to `/auth/callback`; delete it after first use.

## Cloudflare CDN Cache and Set-Cookie Headers

By default Cloudflare does not cache responses containing
`Set-Cookie`. The risk is the inverse: a Cache Rule with an
explicit Edge Cache TTL applied to an auth route strips
`Set-Cookie` and caches the body — the user never gets a
session cookie.

```
# Wrong — strips Set-Cookie silently
Route:  example.com/api/*
Action: Cache Everything, Edge TTL 3600
```

Safe pattern:
```
# Option A — origin declares no-store
Cache-Control: no-store, private

# Option B — Cache Rule bypasses auth routes
Route:  example.com/api/auth/*
Action: Bypass Cache
```

Workers that construct a `Response` directly bypass the CDN
cache layer. A Worker that `fetch()`es an origin and returns
the upstream response is still subject to Cache Rules; ensure
the upstream sets `Cache-Control: no-store` on auth responses.

## Cross-Subdomain Sharing and Storage Access API

`Domain=example.com` shares the cookie with all subdomains.
Setting `Domain=api.example.com` on the session cookie
prevents the SPA and CDN from receiving it — a common mistake
when copy-pasting origin-specific cookie configurations.

For iframes on a **different** registered domain that need
example.com cookies, the Storage Access API is required (Safari
14.5+, Firefox 65+, Chrome 119+). Call it from a user gesture:

```js
// Must be called from a click/tap handler inside the iframe
if (!await document.hasStorageAccess())
  await document.requestStorageAccess();
```

Precondition: the user must have visited `example.com` in
first-party context within the past 30 days. example project embeds
only on same-site subdomains today; this is a contingency path.

## Anti-patterns

- **`document.cookie` for the session** — root cause of the
  ITP 7-day cap; always use `Set-Cookie` from a Worker.
- **`Domain=api.example.com`** — breaks sharing; use
  `Domain=example.com` for all example project session cookies.
- **`SameSite=None` on the primary session cookie** — use
  `Lax` by default; `None` only for explicit embed scenarios.
- **Cache Rule "Cache Everything" over `/api/auth/*`** —
  silently strips `Set-Cookie`; users get no session.

## Gotchas

- **Silent drop of `SameSite=None` without `Secure`.** No
  error; the cookie never appears in requests. Check in
  DevTools → Application → Cookies after each auth call.
- **Safari 12 `SameSite=None` bug.** iOS 12 treated `None`
  as `Strict`. If analytics show >1% iOS 12 users, detect
  via `User-Agent` and omit `SameSite` for those agents.
- **`Max-Age` over `expires`.** Use `Max-Age` (seconds,
  relative) not `expires` (absolute date) to avoid clock-
  skew between server and client.
- **Worker `Headers` deduplicates `Set-Cookie`.** Use
  `headers.append('set-cookie', val)` (lowercase) to emit
  multiple `Set-Cookie` lines without one clobbering another.

## Verification

```sh
# Confirm Worker issues HttpOnly cookie
curl -sI -X POST https://api.example.com/auth/anon \
  | grep -i set-cookie
# Expect: __Secure-anon_sid=...; HttpOnly; Secure; SameSite=Lax

# Confirm CDN does not cache the auth route
curl -sI https://api.example.com/auth/anon \
  | grep -i cf-cache-status
# Expect: BYPASS or MISS — never HIT
```

Manual (iOS Safari):
- DevTools → Storage → Cookies → `example.com`: Expiry ~90 days,
  Domain `.example.com`.
- Trigger OAuth flow with `response_mode=query`; confirm session
  cookie is present in the callback request headers.

## Related

- `documentation/docs/policies/cloudflare/cors-pages-functions.md`
- `documentation/docs/policies/cloudflare/cloudflare-access-jwt-validation.md`
- `documentation/docs/policies/cloudflare/csp-headers-and-cf-waf.md`
- `documentation/docs/policies/cloudflare/ssl-tls-modes-full-strict.md`
- `documentation/docs/policies/cloudflare/workers-best-practices.md`

## Source URLs (verified 2026-08-17)

- WebKit ITP 2.1:
  https://webkit.org/blog/8613/intelligent-tracking-prevention-2-1/
- WebKit ITP 2.2:
  https://webkit.org/blog/8828/intelligent-tracking-prevention-2-2/
- WebKit Storage Access API:
  https://webkit.org/blog/11545/updates-to-the-storage-access-api/
- Cloudflare SameSite cookie interaction:
  https://developers.cloudflare.com/support/account-management-billing/account-privacy-and-security/understanding-samesite-cookie-interaction-with-cloudflare/
- Cloudflare cache behavior (Set-Cookie):
  https://developers.cloudflare.com/cache/concepts/cache-behavior/
- MDN Storage Access API:
  https://developer.mozilla.org/en-US/docs/Web/API/Storage_Access_API/Using
- Chromium SameSite=None incompatible clients:
  https://www.chromium.org/updates/same-site/incompatible-clients/
