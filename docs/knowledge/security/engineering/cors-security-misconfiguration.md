# cors-security-misconfiguration

**Issue:** Insecure CORS configuration allows unauthorized cross-origin access to protected APIs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
APIs that echo the `Origin` request header into `Access-Control-Allow-Origin` without validation allow any site to make credentialed cross-origin requests on behalf of a logged-in user.

## Pattern / Solution
```javascript
// INSECURE — reflects any origin
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin); // NEVER DO THIS
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  next();
});

// SECURE — explicit allowlist
const ALLOWED_ORIGINS = new Set(['https://app.example.com', 'https://admin.example.com']);
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (ALLOWED_ORIGINS.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Vary', 'Origin');
  }
  next();
});
```

## Gotchas
- Always add `Vary: Origin` when dynamically setting `Access-Control-Allow-Origin` to prevent cache poisoning.
- Null origin (`Origin: null`) is sent from sandboxed iframes and `file://` — never allowlist it.
- Subdomain wildcards (`*.example.com`) are not supported by browsers; you must maintain an explicit list.
- Pre-flight OPTIONS requests must also be handled and return the correct CORS headers.

## Related
- `cors-wildcard-with-credentials.md`
- `csrf-vs-cors-vs-samesite.md`
