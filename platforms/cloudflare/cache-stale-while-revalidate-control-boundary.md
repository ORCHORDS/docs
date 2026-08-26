# Cache stale-while-revalidate control boundary

**Issue:** Cloudflare’s asynchronous `stale-while-revalidate` serves expired content immediately while one background revalidation runs. That improves latency and origin load, but can expose stale authorization, pricing, configuration, or release data beyond its freshness lifetime.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Classify each response by the maximum acceptable stale window; do not use stale serving for user-specific, authorization-sensitive, or safety-critical state.
- Emit a bounded `max-age` and `stale-while-revalidate` policy only for cacheable responses.
- Provide stable `ETag` or `Last-Modified` validators where possible and make origin revalidation cheap.
- Use Cache Rules to disable serving stale during revalidation on routes that must block for fresh data.
- If browser and edge TTLs must differ, use Edge Cache TTL rather than `s-maxage` when asynchronous stale serving is required.
- Include every representation-changing input in the cache key or `Vary` policy, and define purge behavior for emergency changes.
- Monitor `CF-Cache-Status`, content age, revalidation duration, and origin errors.

## Implementation and tests

Prime an object, let it expire, and send parallel requests inside the allowed stale window. Assert that the first and concurrent requests receive the old representation with `CF-Cache-Status: UPDATING`, then assert a later request receives the refreshed representation with `HIT`. Test validators returning both 304 and a changed body.

Repeat with `must-revalidate`, `proxy-revalidate`, `s-maxage`, and `no-cache` while Origin Cache Control is enabled; Cloudflare documents these combinations as preventing stale service and producing the synchronous `EXPIRED` path. Test the Cache Rule override and purge path at the edge.

## Gotchas and applicability

Asynchronous revalidation means even the triggering request receives stale content. `s-maxage` implies shared-cache revalidation semantics here and conflicts with the desired stale path. Smart Edge Revalidation can synthesize a `Last-Modified` value when origin validators are absent, but origin-provided validators give clearer change control.

This describes Cloudflare CDN cache behavior, not an application-level Worker cache implementation or a durability guarantee.

## Official sources

- [Cloudflare Cache: Revalidation](https://developers.cloudflare.com/cache/concepts/revalidation/)
- [Cloudflare Cache: Cache-Control directives](https://developers.cloudflare.com/cache/concepts/cache-control/)
- [Cloudflare Cache: Response statuses](https://developers.cloudflare.com/cache/concepts/cache-responses/)
