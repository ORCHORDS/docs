# ttfb-optimization

**Issue:** Time to First Byte exceeds 800ms
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
TTFB measures server response time and network latency combined. It is the single biggest lever for LCP on server-rendered pages. Google's threshold for good is < 800ms.

## Pattern / Solution
1. Move origin server closer to users via CDN edge workers.\n2. Stream HTML responses with Transfer-Encoding: chunked so the browser parses early.\n3. Cache full HTML pages at the CDN layer for anonymous traffic.\n4. Optimize database queries that block the first byte.\n5. Enable HTTP/2 or HTTP/3 to reduce connection overhead.

## Gotchas
- Authentication bypasses CDN caching; consider edge-side partial caching or stale-while-revalidate.\n- Slow DNS resolution adds to TTFB; measure with WebPageTest's waterfall breakdown.\n- Node.js event loop lag under load delays responses even if query times are fast.

## Related
lcp-optimization, http2-multiplexing, cdn-cache-strategy, cloudflare-workers-performance, nodejs-event-loop-lag
