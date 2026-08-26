# x-frame-options-vs-csp

**Issue:** Choosing and combining X-Frame-Options and CSP frame-ancestors to prevent clickjacking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Clickjacking embeds your page in an invisible iframe on an attacker-controlled site. Users interact with your page without realizing it — triggering payments, account changes, or data exfiltration.

## Pattern / Solution
```http
# Legacy — supported everywhere but coarse
X-Frame-Options: DENY
# or allow same origin only
X-Frame-Options: SAMEORIGIN

# Modern — use CSP frame-ancestors (overrides X-Frame-Options in modern browsers)
Content-Security-Policy: frame-ancestors 'none';
Content-Security-Policy: frame-ancestors 'self' https://partner.example.com;
```
Send both headers for maximum compatibility. `frame-ancestors` wins in browsers that support CSP Level 2+.

## Gotchas
- `X-Frame-Options: ALLOW-FROM uri` is deprecated and ignored by Chrome/Firefox — use CSP instead.
- `frame-ancestors` only works in the `Content-Security-Policy` header, not `Content-Security-Policy-Report-Only` for enforcement.
- Embedding your own page in a legitimate iframe (e.g., widget) requires `frame-ancestors 'self'`, not `'none'`.
- Meta tag CSP does not support `frame-ancestors` — must be a header.

## Related
- `http-security-headers-hsts.md`
- `csp-deep-2026.md`
- `clickjacking-defense.md`
