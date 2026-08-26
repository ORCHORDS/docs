# cdn-architecture

**Issue:** Static assets and cacheable responses are served from origin at high latency and cost
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users in Asia experience 300ms TTFB for a service hosted in US-East because every request hits origin.

## Pattern / Solution
Distribute cacheable content across edge PoPs geographically close to users. Configure correct Cache-Control headers. Use cache-busting via content-hash filenames for static assets. Implement CDN-level rules for dynamic content caching with Vary headers.

## Gotchas
Aggressive CDN caching of authenticated content leaks data between users. Purge APIs are eventually consistent; do not rely on instant propagation. Origins must handle cache misses gracefully during purge storms.

## Related
edge-computing-patterns, tenant-routing-patterns, cache-aside-pattern
