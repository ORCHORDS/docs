# permissions-policy-header

**Issue:** Missing Permissions-Policy header leaves browser features (camera, mic, geolocation) accessible to embedded scripts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Third-party scripts injected via XSS or supply-chain compromise can invoke powerful browser APIs (camera, microphone, payment) unless explicitly restricted. Permissions-Policy (formerly Feature-Policy) lets you deny these at the HTTP layer.

## Pattern / Solution
```http
# Deny all sensitive features unless explicitly needed
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()

# Allow geolocation only for same origin
Permissions-Policy: geolocation=(self), camera=(), microphone=()
```
```nginx
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
```

## Gotchas
- Syntax changed from Feature-Policy (comma-separated) to Permissions-Policy (allow-list syntax) — old syntax is ignored in modern browsers.
- `interest-cohort=()` opts out of FLoC/Topics API tracking — include it as a privacy default.
- iframe `allow` attribute also restricts features per-frame — both header and attribute must permit for iframes.
- Overly restrictive policies break legitimate features silently; test with DevTools.

## Related
- `referrer-policy-patterns.md`
- `security-headers-comprehensive.md`
