# r2-etag-conditional-request

**Issue:** R2 returns a strong ETag but the format differs from S3, breaking clients that assume S3-compatible ETag format
**Date:** 2026-08-11
**Status:** documented

## Symptom
A client library that caches based on `ETag` and sends `If-None-Match` gets unexpected 200 responses instead of 304s. Or an S3-compatible tool rejects the R2 ETag as malformed.

## Root cause
S3 computes the ETag as the MD5 of the object content (for single-part uploads) and a composite hash for multipart. R2 uses a different hash algorithm (not MD5). Clients hardcoded to validate ETag format or compute expected ETags from content will mismatch.

## Fix
Treat R2 ETags as opaque strings — store and compare them verbatim, never compute them from content:
```ts
const obj = await env.R2.get(key);
const etag = obj?.etag; // treat as opaque

// Conditional fetch
const conditional = await env.R2.get(key, {
  onlyIf: { etagMatches: storedEtag },
});
if (!conditional) {
  // 304 equivalent — object hasn't changed
}
```

## Detection
```
grep -rn "etag\|ETag" src/ --include="*.ts" | grep "md5\|hash\|compute"
```

## Related
- `kv-metadata-size-limit.md`
- `cache-api-vary-header.md`
