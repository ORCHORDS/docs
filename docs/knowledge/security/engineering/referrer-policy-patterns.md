# referrer-policy-patterns

**Issue:** Misconfigured Referrer-Policy leaks sensitive URL parameters to third parties
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
URLs often contain tokens, user IDs, or search queries in query strings. When users click external links, the browser sends the full URL as the `Referer` header, exposing this data to third-party servers and analytics.

## Pattern / Solution
```http
# Recommended default — full URL same-origin, only origin cross-origin
Referrer-Policy: strict-origin-when-cross-origin

# Maximum privacy — no referrer ever
Referrer-Policy: no-referrer

# Per-link override in HTML
<a href="https://external.example" referrerpolicy="no-referrer">Link</a>
```
```nginx
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

## Gotchas
- `unsafe-url` (browser default pre-2020) sends the full URL everywhere — never use.
- `origin-when-cross-origin` sends full URL on same-origin navigations including to subdomains — may leak.
- OAuth redirect URIs with tokens in the URL + a third-party analytics script = token leakage without this header.
- Referrer-Policy can also be set via `<meta name="referrer">` but header takes precedence.

## Related
- `http-security-headers-hsts.md`
- `permissions-policy-header.md`
