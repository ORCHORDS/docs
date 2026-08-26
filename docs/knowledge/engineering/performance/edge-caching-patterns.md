# edge-caching-patterns

**Issue:** Personalized or dynamic content cannot be cached at the CDN edge
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Fully dynamic responses bypass CDN caches. Edge computing allows partial caching, content assembly at the edge, and personalization without full origin round trips.

## Pattern / Solution
1. Fragment caching: cache page shell at edge; fetch personalized fragments from origin.\n2. Edge-side includes (ESI): assemble cached fragments at the edge for personalized pages.\n3. Cache API responses with short TTLs at the edge using cf: { cacheTtl: 60 } in Workers.\n4. Use KV or Durable Objects for user-session data at the edge.\n5. Stale-while-revalidate at edge: serve cached response; trigger async origin refresh.

## Gotchas
- Edge Workers have CPU time limits (10-50ms); avoid complex computations.\n- Debugging edge cache behavior requires edge-specific tooling (Cloudflare Logs, Wrangler tail).\n- GDPR considerations: caching user data at edge PoPs in multiple jurisdictions.

## Related
cdn-cache-strategy, cloudflare-workers-performance, kv-read-performance
