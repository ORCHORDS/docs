# cache-api-vary-header

**Issue:** Cloudflare Cache API ignores `Vary` headers, caching the wrong variant for different `Accept` or `Accept-Encoding` values
**Date:** 2026-08-11
**Status:** documented

## Symptom
A response cached for `Accept: application/json` is served to a client that sent `Accept: text/html`, returning JSON to a browser expecting HTML. Or a compressed response is served to a client that doesn't support gzip.

## Root cause
Cloudflare's Cache API does not implement `Vary` header semantics. It caches responses keyed only by URL (and optionally custom cache keys). The `Vary` header in the response is stored but not respected during cache lookup.

## Fix
Encode the varying dimension into the cache key URL:
```ts
const cacheKey = new Request(
  `${request.url}?__accept=${request.headers.get('Accept') ?? 'default'}`,
  request
);
const cached = await cache.match(cacheKey);
// ...
await cache.put(cacheKey, response.clone());
```
Or use separate URL paths for different content types.

## Detection
```
grep -rn "Vary" src/ --include="*.ts"
grep -rn "cache.put\|cache.match" src/ --include="*.ts"
```

## Related
- `response-clone-pattern.md`
- `r2-etag-conditional-request.md`
