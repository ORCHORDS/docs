# etag-conditional-requests

**Issue:** Unchanged resources consume bandwidth on repeat requests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ETags and Last-Modified headers enable conditional requests (304 Not Modified). The browser sends If-None-Match or If-Modified-Since; the server responds with 304 and no body if unchanged.

## Pattern / Solution
1. Ensure your server sends ETag or Last-Modified headers for cacheable resources.\n2. Nginx: enabled by default; verify with curl -I https://example.com/style.css.\n3. Express: use express.static with default etag; or res.set('ETag', hash) manually.\n4. CDNs add ETags automatically; don't disable them.\n5. Combine with Cache-Control: no-cache for HTML so browsers always revalidate but save bandwidth.

## Gotchas
- Weak ETags (W/...) allow semantic equivalence; strong ETags require byte-for-byte identity.\n- ETags across load-balanced servers must be consistent; avoid timestamp-based ETags in clusters.\n- 304 responses still require a round trip; immutable hashed assets are faster (no round trip).

## Related
cache-control-headers, cdn-cache-strategy
