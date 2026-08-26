# response-clone-pattern

**Issue:** Not cloning a Response before passing it to `cache.put()` makes the body unavailable for further use
**Date:** 2026-08-11
**Status:** documented

## Symptom
After calling `cache.put(request, response)` in a Service Worker or Cloudflare Worker, attempting to read `response.json()` throws "body used already" because `cache.put` consumes the body stream.

## Root cause
`Cache.put()` reads and stores the response body. If the same `Response` object is passed, the stream is consumed. Any subsequent read of the original response will find an exhausted stream.

## Fix
```ts
// Wrong — response body is consumed by cache.put
const response = await fetch(request);
await cache.put(request, response);
return response; // body used already!

// Correct — clone before caching
const response = await fetch(request);
await cache.put(request, response.clone());
return response; // original is still readable
```

## Detection
```
grep -rn "cache.put" src/ --include="*.ts" | grep -v "clone()"
```

## Related
- `fetch-body-consumed-twice.md`
- `cache-api-vary-header.md`
