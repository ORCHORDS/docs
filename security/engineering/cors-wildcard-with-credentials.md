# cors-wildcard-with-credentials

**Issue:** Combining Access-Control-Allow-Origin wildcard with credentials causes browser rejection and security confusion
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers set `Access-Control-Allow-Origin: *` for public APIs, then add `Access-Control-Allow-Credentials: true` when authentication is needed. Browsers reject this combination, but some server frameworks allow it silently, creating a false sense of security or runtime errors.

## Pattern / Solution
```http
# INVALID — browsers reject this combination
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true

# VALID for public read-only APIs
Access-Control-Allow-Origin: *
# (omit Credentials header)

# VALID for credentialed requests — must name the specific origin
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```
```javascript
// Middleware pattern: public endpoints use *, private use allowlist
function corsMiddleware(isPublic) {
  return (req, res, next) => {
    if (isPublic) {
      res.setHeader('Access-Control-Allow-Origin', '*');
    } else {
      const origin = req.headers.origin;
      if (allowlist.has(origin)) {
        res.setHeader('Access-Control-Allow-Origin', origin);
        res.setHeader('Access-Control-Allow-Credentials', 'true');
        res.setHeader('Vary', 'Origin');
      }
    }
    next();
  };
}
```

## Gotchas
- CORS does not protect server-to-server requests — only browser-enforced.
- `credentials` in `fetch()` includes cookies, Authorization headers, and TLS client certs.
- Some CDNs cache CORS preflight — ensure `Vary: Origin` propagates to the CDN config.
- A wildcard is fine for public asset CDNs, dangerous for API endpoints.

## Related
- `cors-security-misconfiguration.md`
- `csrf-vs-cors-vs-samesite.md`
