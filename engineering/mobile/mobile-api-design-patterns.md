# mobile-api-design-patterns

**Issue:** Designing backend APIs optimized for mobile clients
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mobile APIs have different constraints than web APIs: unreliable connections, limited battery, smaller payloads, and offline-first requirements. Generic REST APIs designed for web clients often perform poorly on mobile.

## Pattern / Solution
**Pagination with cursor (not offset):**
```json
GET /api/feed?cursor=eyJpZCI6MTAwfQ&limit=20

{
  "data": [...],
  "pagination": {
    "nextCursor": "eyJpZCI6ODB9",
    "hasMore": true
  }
}
```

**Sparse fieldsets (reduce payload):**
```
GET /api/users/42?fields=id,name,avatar_url
```

**Batch requests:**
```json
POST /api/batch
[
  { "method": "GET", "path": "/users/42" },
  { "method": "GET", "path": "/posts?userId=42&limit=5" }
]
```

**Conditional requests (ETag / If-None-Match):**
```http
GET /api/config
ETag: "abc123"

→ 304 Not Modified (no body) if unchanged
→ 200 with new body + new ETag if changed
```

**Delta sync:**
```
GET /api/posts?since=2026-08-01T00:00:00Z&deleted=true
```
Return only changed/deleted records since last sync timestamp.

**Retry-After header for rate limits:**
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
```

## Gotchas
- Offset pagination causes duplicate/missing items on insertions between pages; always use cursor-based for feeds
- Avoid deeply nested JSON; each level adds parsing overhead on low-end devices
- Compress responses with gzip/brotli — a 2G connection makes payload size critical
- Return `Content-Length` for progress indicators on large downloads
- Idempotency keys prevent duplicate transactions on retry after network timeout
- Never return 200 with an error body; mobile clients typically branch on status code, not body content

## Related
- `react-native-offline-first.md`
- `mobile-offline-sync-conflict-resolution.md`
- `mobile-auth-oauth-pkce.md`
- `mobile-performance-profiling.md`
