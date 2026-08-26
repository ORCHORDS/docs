# clickjacking-defense

**Issue:** Clickjacking via iframe + X-Frame-Options / CSP
**Date:** 2026-08-09
**Status:** documented

## Symptom
A malicious site embeds your app in an iframe. The user sees
your "Delete Account" button but is actually clicking the
attacker's "Transfer Money" button (or a different element
on your page, hidden behind the iframe). The user thinks they
clicked one thing but actually clicked another.

## Root cause
**Clickjacking** is when an attacker embeds your site in an
iframe and uses CSS to position a transparent decoy over
the attacker's intended click target. The user thinks they're
clicking the iframe's content but is actually clicking
something on the parent page (or vice versa).

**Source:** OWASP — Clickjacking Defense Cheat Sheet:
https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html

> "Clickjacking is an attack that tricks a user into clicking
> on something different from what the user perceives."

## The attack

```html
<!-- attacker.com -->
<iframe src="https://victim.com/transfer?amount=1000&to=attacker"
        style="opacity: 0.1; position: absolute; top: 0; left: 0;
               width: 100%; height: 100%; z-index: 1;"></iframe>
<button style="position: absolute; top: 100px; left: 100px;
               z-index: 2;">Click for free prize!</button>
```

The user sees "Click for free prize!" but is actually clicking
the iframe's "Transfer $1000" button (because the iframe is on
top of the button, with low opacity).

## Fix

### 1. X-Frame-Options header
```http
X-Frame-Options: DENY
```

Three values:
- `DENY` — never allow the page to be in an iframe
- `SAMEORIGIN` — allow iframes from the same origin
- `ALLOW-FROM uri` — allow iframes from a specific URI
  (deprecated)

For most apps, `DENY` is the right choice.

### 2. Content-Security-Policy frame-ancestors
```
Content-Security-Policy: frame-ancestors 'none';
```

`frame-ancestors` is the modern equivalent of
`X-Frame-Options`. It supports more options:
- `'none'` — no iframes
- `'self'` — same origin only
- `https://trusted-partner.com` — specific origin
- `*` — all origins (NOT recommended)

CSP `frame-ancestors` overrides `X-Frame-Options` in modern
browsers. Set both for backward compatibility.

### 3. Same-origin check in JavaScript
For defense in depth, add a JS check:
```ts
if (window.top !== window.self) {
  // The page is in an iframe
  document.body.innerHTML = '';
  throw new Error('This page cannot be embedded');
}
```

This catches the case where the headers are stripped (e.g.
a misconfigured proxy).

### 4. Frame-busting cookies
For highly sensitive operations (banking, payments), set a
"frame-busting" cookie that's required:
```ts
// On a sensitive page
if (!request.headers.get('cookie')?.includes('frame-bust=1')) {
  // Set the cookie
  response.headers.set('Set-Cookie', 'frame-bust=1; HttpOnly; Secure; SameSite=Strict');
}
```

If the cookie is missing, the iframe is suspicious. This is
rarely used; the headers are usually enough.

### 5. CSP for iframes in your own app
If your app legitimately uses iframes (e.g. embedded videos),
allow them:
```
Content-Security-Policy: frame-src 'self' https://www.youtube.com
```

This controls what your app can embed, not what can embed your
app.

## Verification
- **Test:** `test/clickjacking.test.ts > X-Frame-Options: DENY
  set on all responses` — passes
- **Test:** `test/clickjacking.test.ts > CSP frame-ancestors
  'none' set` — passes
- **Live:** Browser DevTools shows the X-Frame-Options + CSP
  headers
- **Pen test:** Annual third-party clickjacking scan

## Gotchas
- **A malicious site can set `X-Frame-Options` on its own
  responses.** That doesn't help your site. The header must
  be on YOUR response, set by YOUR server.
- **Some browsers ignore `X-Frame-Options` for sandboxed
  iframes.** Use CSP `frame-ancestors` as the modern defense.
- **The "frame-busting" JS check is bypassable.** An attacker
  can set `sandbox="allow-scripts"` on the iframe, which
  prevents the parent's JS from being blocked. The HTTP
  headers are the real defense.
- **Some legitimate use cases require iframes** (e.g. a
  payment iframe). For these, use `frame-ancestors 'self'`
  (same-origin only) or specific allowlist.
- **CF Pages Functions set `X-Frame-Options: DENY` by default**
  for static assets. Verify it's set for dynamic responses too.

## Related
- `csp-headers-and-cf-waf.md` (the broader CSP story)
- `secure-headers.md` (the full set of headers)
- `xss-prevention.md` (related client-side attack)
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html
