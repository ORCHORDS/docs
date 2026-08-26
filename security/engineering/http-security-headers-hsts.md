# http-security-headers-hsts

**Issue:** HTTP Strict Transport Security misconfiguration leaves sites vulnerable to downgrade attacks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Sites served over HTTPS without HSTS allow attackers to intercept the first HTTP request before the browser upgrades to HTTPS. First-visit hijacking and SSL stripping attacks exploit this window.

## Pattern / Solution
```nginx
# Nginx — set HSTS with preload
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
```
```http
# Minimum viable for production
Strict-Transport-Security: max-age=31536000; includeSubDomains
```
- Submit to https://hstspreload.org once `preload` directive is stable.
- Start with `max-age=300` in staging; ramp to 63072000 after confirming all subdomains serve HTTPS.

## Gotchas
- `includeSubDomains` breaks any HTTP-only subdomain — audit all before enabling.
- Removing HSTS takes `max-age` seconds to take effect; set a short max-age first when testing removal.
- Preload list removal takes weeks; don't add `preload` until the full domain is HTTPS-only permanently.
- Load balancers may strip the header — set it at the load-balancer layer, not only in app code.

## Related
- `security-headers-comprehensive.md`
- `x-frame-options-vs-csp.md`
