# content-negotiation-vary-header

**Issue:** Setting the Vary response header correctly for locale-negotiated content
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CDN and browser caches serve stale locale content when the `Vary` header is missing or incorrect.

## Pattern / Solution
For locale-specific HTML:
```http
HTTP/1.1 200 OK
Content-Language: fr
Vary: Accept-Language
Cache-Control: public, max-age=3600
```
For cookie-based locale:
```http
Vary: Cookie
```
Express middleware:
```js
app.use((req, res, next) => {
  res.vary('Accept-Language');
  next();
});
```
Best practice: use locale in URL path instead of header negotiation:
```
/fr/about  ->  Cache-Control: public, max-age=86400  (no Vary needed)
```

## Gotchas
- `Vary: *` disables caching entirely -- never use for locale content
- Some older CDNs ignore `Vary: Accept-Language`; test with `curl -H "Accept-Language: fr"`
- URL-based locale is simpler and more cache-friendly than header negotiation

## Related
- `locale-negotiation-accept-language.md`
- `hreflang-seo-2026.md`
