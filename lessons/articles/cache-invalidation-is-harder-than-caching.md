# cache-invalidation-is-harder-than-caching

**Issue:** Adding a cache is easy; keeping it consistent with the source of truth is where teams get burned
**Date:** 2026-08-11
**Status:** documented

## What happened
A product prices cache was added to eliminate database load. The cache had a 10-minute TTL. A price change was applied in the admin panel and confirmed by the admin. Customers saw the old price for up to 10 minutes. Some completed purchases at the wrong price. The reconciliation took two weeks.

## The lesson
Before adding a cache, define precisely how and when it will be invalidated. Options: TTL (simple, but stale window), event-driven invalidation (publish a cache-bust event on every write), write-through (write to cache and DB simultaneously), and cache-aside with version tags. Choose intentionally, not by default.

## Why it matters
A stale cache is often worse than no cache: it serves confidently incorrect data. Users trust what they see. Wrong prices, wrong inventory, wrong permissions — all have real business consequences.

## How to apply
- [ ] Before implementing a cache, document: what is cached, what invalidates it, and the acceptable staleness window.
- [ ] For user-facing pricing or inventory, use event-driven invalidation, not TTL alone.
- [ ] Add cache hit/miss metrics to your observability stack from day one.
- [ ] Test invalidation paths explicitly: write a test that updates the source and asserts the cache is stale within one read.
- [ ] Consider whether you need a cache at all before adding one — sometimes a better query is enough.

## Related
- `n-plus-one-queries-compound-at-scale.md`
- `eventual-consistency-surprises-clients.md`
