# anonymous-auth-jwt-mobile-storage

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

An anonymous mobile-web user's session token is stolen via an
injected in-app-browser script, or the session breaks silently
after a cookie prune by Safari ITP or an iOS 18 WKWebView
SameSite policy change. No credentials exist to recover with —
the user's 21+ age-gate compliance state is gone.

## Context

Platform: Next.js static export on Cloudflare Pages, auth via
Cloudflare Workers. Users are fully anonymous (no credentials).
The platform must maintain stable session identity across app
restarts, satisfy a per-session 21+ compliance gate, and remain
functional inside iOS in-app browsers (WKWebView). Key
constraints: no persistent user ID exposed to client JS; no
login prompt on restart; native WebView injection must not be
able to steal session tokens.

---

## 1. Why localStorage JWT Storage Is Dangerous on Mobile Web

Any JavaScript on the page — injected ad tags, analytics
scripts, or native-app-injected WKWebView code — can call
`localStorage.getItem('token')`. On mobile WebViews, the native
host injects JS directly into the page context without needing
a CSP bypass. There is no client-side mitigation.

Rule: hold the access token in a JS-memory variable only (lost
on page close, intentionally). Store the refresh token in an
HttpOnly `Set-Cookie` header from the Worker — unreachable
by JS, including injected scripts.

## 2. HttpOnly Cookie vs localStorage for Anonymous Sessions

HttpOnly server-set cookies are the only safe bearer-token
store on mobile web. Key trade-offs:

- **XSS / injection:** HttpOnly cookies are not readable by
  any JS; localStorage is fully readable.
- **CSRF:** cookies require `SameSite=Lax` + a CSRF token on
  state-changing POSTs; localStorage does not.
- **Safari ITP 7-day cap:** applies only to cookies written via
  `document.cookie` (JS-set). Cookies issued via `Set-Cookie`
  on a genuine first-party host (same registrable domain, not
  CNAME-cloaked) follow their declared `Max-Age` without
  truncation, provided `Secure` and `SameSite` are present.

Implication: always use `Set-Cookie` from the Worker for any
session-bearing value. Never use `document.cookie`.

## 3. SameSite=Lax/Strict Across iOS Safari and WKWebView

iOS requires all browsers to use WebKit, so every in-app
browser (Instagram, TikTok, Twitter/X) runs WKWebView. iOS 18
introduced an undocumented breaking change: WKWebView default
`SameSite` shifted from None to Lax, and JS-set `SameSite=None`
cookies are silently downgraded to Lax.

| Context                          | iOS ≤17    | iOS 18+       |
|----------------------------------|------------|---------------|
| JS-set SameSite=None             | Accepted   | Downgraded Lax|
| Server Set-Cookie SameSite=None  | Accepted   | Accepted*     |
| Server Set-Cookie SameSite=Lax   | Sent on nav| Sent on nav   |
| SameSite=Lax cross-site POST     | Blocked    | Blocked       |

*Requires `Secure` flag; iOS 18 rejects `SameSite=None`
without it.

`SameSite=Strict` breaks OAuth callbacks and magic-link
redirects. `SameSite=Lax` is correct: top-level navigations
carry the cookie; cross-site sub-resource requests do not.

```http
Set-Cookie: __Secure-rt=<token>; HttpOnly; Secure;
  SameSite=Lax; Path=/api/auth; Max-Age=2592000
```

## 4. ITP and Cookie Partitioning in Third-Party Contexts

**ITP (Safari 17+ / iOS 17+):**
- Third-party cookies: blocked entirely.
- JS-set first-party cookies: capped at 7 days if the domain
  is classified as a cross-site tracker.
- Server-set first-party cookies on non-CNAME-cloaked hosts:
  follow declared `Max-Age` when `Secure` + `SameSite` set.

**Storage Access API** — not a silent fallback. Calls require
a user gesture, display a browser prompt, and are auto-rejected
by Safari if the origin has had no recent first-party
interaction. Anonymous flows that depend on it stall visibly.

**CHIPS (Safari 18.4+):** The `Partitioned` attribute scopes a
cookie to top-level site + cookie domain, preventing cross-site
tracking. If the Worker is embedded as an iframe, issue a
separate partitioned cookie alongside the standard one:

```http
Set-Cookie: __Secure-embed-sid=<tok>; HttpOnly; Secure;
  SameSite=None; Partitioned; Path=/; Max-Age=3600
```

CHIPS and ITP are orthogonal: CHIPS partitions state; ITP
blocks tracker-domain cookies. A partitioned cookie on a
tracked domain is still blocked by ITP.

Mitigation: keep the auth Worker on the same registrable domain
(`api.example project.example.com` for `example project.example.com`). ITP does not
treat same-site subdomains as third parties.

## 5. Short-lived Access Token + Refresh Token Rotation

The Worker is the sole token issuer. Access tokens are 15 min,
held in JS memory. Refresh tokens live in HttpOnly cookies.
Each rotation invalidates the previous refresh token; a reused
token signals theft and kills the session.

```ts
// Worker: POST /api/auth/refresh
const rt     = getCookie(req, '__Secure-rt');
const stored = await env.KV.get(`rt:${rt}`, 'json') as
  { sub: string; used: boolean } | null;

if (!stored || stored.used) {
  await env.KV.delete(`rt:${rt}`); // revoke family on reuse
  return new Response('Unauthorized', { status: 401 });
}
const newRt = crypto.randomUUID();
const at    = await signJwt(
  { sub: stored.sub, exp: now() + 900 }, env.JWT_SECRET
);
await Promise.all([
  env.KV.put(`rt:${newRt}`,
    JSON.stringify({ sub: stored.sub, used: false }),
    { expirationTtl: 2_592_000 }),
  env.KV.delete(`rt:${rt}`),
]);
return new Response(JSON.stringify({ accessToken: at }), {
  headers: {
    'Content-Type': 'application/json',
    'Set-Cookie':
      `__Secure-rt=${newRt}; HttpOnly; Secure; ` +
      `SameSite=Lax; Path=/api/auth; Max-Age=2592000`,
  },
});
```

**`__Secure-` prefix:** browser accepts the cookie only if the
response was served over HTTPS and the `Secure` flag is
present. Cloudflare Workers always serve HTTPS in production.
In local `wrangler dev` (`http://`), the prefix is silently
dropped — gate on an `ENVIRONMENT` Worker binding.

## 6. Device Fingerprinting for Anonymous Session Continuity

When the HttpOnly cookie is cleared (browser data wipe, app
reinstall), use a server-computed device fingerprint as a
recovery hint. Derive it from request headers, key it with an
HMAC secret, and store only the hash server-side — never the
raw signals.

```ts
function deviceHash(req: Request, key: string): string {
  const ua      = req.headers.get('User-Agent')      ?? '';
  const lang    = req.headers.get('Accept-Language') ?? '';
  const country = req.headers.get('CF-IPCountry')    ?? '';
  // CF-IPCountry is country-level only — not the raw IP
  return hmacSha256(`${ua}|${lang}|${country}`, key);
}
```

Supplement with an IndexedDB opaque UUID where storage persists;
treat the fingerprint as a last-resort fallback, not primary.
Rotate `FINGERPRINT_KEY` annually to invalidate stale hashes.
Never store raw user-agent strings or IP addresses in session
records; store only the keyed HMAC output.

## Anti-patterns

- **localStorage for any refresh token.** XSS or WKWebView host
  injection exfiltrates it before any rate limit fires.
- **Access tokens valid >30 min.** A leaked token is a long-
  lived credential; 15 min is the practical ceiling.
- **JS-set `SameSite=None` on iOS 18.** Silently downgraded to
  Lax; cross-origin auth flows break without warning.
- **`document.cookie` for session identity.** ITP caps at 7
  days on tracker-classified domains. Use `Set-Cookie`.
- **Storage Access API as silent fallback.** Always shows a
  browser prompt; anonymous flows stall visibly.
- **`Path=/` on the refresh token cookie.** Sends the RT on
  every API call. Scope to `Path=/api/auth` only.

## Gotchas

- **`__Secure-` cookies silently drop under `wrangler dev`.**
  `http://localhost` makes the browser reject the prefix with
  no console error. Gate cookie name on env.
- **KV is eventually consistent — RT rotation is not atomic.**
  Two rapid refresh calls can both read `used: false` before
  either write lands. Use a Durable Object or D1 serializable
  transaction for the check-and-rotate step.
- **ITP 7-day cap is JS-cookie-only.** A `Set-Cookie` header on
  a non-cloaked first-party host is not capped; `document
  .cookie` on the same domain is. The distinction matters for
  any CNAME-proxied third-party analytics endpoint.
- **iOS 18 WKWebView SameSite=None change is undocumented.**
  No Apple changelog entry exists; behavior confirmed via Apple
  Forums thread 765199 (see Source URLs).
- **CHIPS `Partitioned` + ITP are not the same fix.** `Parti-
  tioned` stops cross-site state sharing between top-level
  sites; ITP still blocks cookies from tracked domains.

## Verification

```sh
# 1. Cookie flags on anonymous session issuance
curl -sI https://api.example project.example.com/api/auth/anon \
  | grep -i set-cookie
# Expect: __Secure-rt=…; HttpOnly; Secure; SameSite=Lax
#         Path=/api/auth; Max-Age=2592000

# 2. Not JS-readable (DevTools Console)
#    document.cookie  →  must not contain 'rt'

# 3. RT rotation rejects reuse
#    POST /api/auth/refresh (valid RT)      → 200
#    POST /api/auth/refresh (same RT again) → 401

# 4. Safari ITP simulation
#    Safari > Develop > ITP Debug Mode; advance 8 days
#    Server-set cookie present; JS-set cookie pruned

# 5. iOS 18 WKWebView
#    Load PWA in WKWebView test harness; verify
#    SameSite=Lax cookie present in subsequent requests
```

## Related

- `documentation/docs/policies/security/jwt-best-practices.md`
- `documentation/docs/policies/security/session-cookies-vs-jwt.md`
- `documentation/docs/policies/security/csrf-protection-double-submit.md`
- `security/content-security-policy-csp-modern-deployment.md`
- `documentation/docs/policies/cloudflare/` — Worker auth patterns

## Source URLs (verified 2026-08-17)

- WebKit ITP — full third-party cookie blocking:
  https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
- WebKit Tracking Prevention reference:
  https://webkit.org/tracking-prevention/
- Storage Access API (MDN):
  https://developer.mozilla.org/en-US/docs/Web/API/Storage_Access_API
- iOS 18 WKWebView default SameSite change (Apple Forums):
  https://developer.apple.com/forums/thread/765199
- iOS 18.4.1 WKWebView cookie requirements (community notice):
  https://forums.appos.io/discussion/10/
- ITP 7-day cap — server-set vs JS-set analysis:
  https://snowplow.io/blog/tracking-cookies-length
- Auth in hybrid mobile apps — WKWebView pitfalls (DEV):
  https://dev.to/itamartati/understanding-authentication-in-hybrid-mobile-apps-cookies-webviews-and-common-pitfalls-3m8
- JWT auth with Cloudflare Workers:
  https://drcodes.com/posts/jwt-authentication-with-cloudflare-workers-complete-guide
- RFC 6265bis Cookie spec (current IETF draft):
  https://datatracker.ietf.org/doc/html/draft-ietf-httpbis-rfc6265bis
- MDN Secure cookie implementation guide:
  https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies
