# cache-stampede-prevention

**Issue:** A popular cache entry expires, and hundreds of concurrent requests that would normally be served from cache all miss at once, each independently recomputing the same expensive value (a heavy query or an upstream API call). The origin or database absorbs a synchronized burst it was sized to handle for one request, latency spikes for exactly the duration of the TTL window, and in the worst case the added load slows computation down further, causing cascading timeouts. This article covers the failure modes of cache expiry under concurrency and the standard prevention techniques: request coalescing, distributed locking, probabilistic early expiration, stale-while-revalidate, and refresh-ahead.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Failure Modes

1. **Expiry stampede (thundering herd on miss).** When a hot key's TTL lapses, every in-flight request pays the recomputation cost simultaneously; with a 2-second rebuild and 500 req/s, roughly 1000 requests queue behind the same answer. The signature symptom is sawtooth latency that peaks at each TTL boundary.
2. **Cold-start stampede.** After a deploy or cache flush, an entire key population misses at once, not just one key; restarts turn into self-inflicted load tests on the origin. Mitigation belongs in deployment design (pre-warming, gradual rollout), not only in per-key logic.
3. **Retry amplification.** Clients that time out and retry during a stampede multiply the very requests causing it; each retry re-enters the miss path because the value still does not exist. Timeouts shorter than the rebuild time guarantee duplicate work.
4. **Eviction-cascade misses.** Under memory pressure a cache evicts a cluster of related keys, and the subsequent miss storm both serves slow responses and allocates new memory, triggering further eviction — a feedback loop. The stampede here is caused by sizing, not TTL.
5. **Failed recomputation storms.** If the origin errors during the burst (connection pool exhausted by the miss wave), no request writes a fresh value, so the next wave also misses; errors must extend or preserve the stale entry rather than leaving a hole. An empty value at the key is the worst possible post-failure state.

## Prevention Techniques

1. **Request coalescing (singleflight).** Within one process, collapse concurrent lookups of the same key into a single in-flight computation whose result is shared — Go's `singleflight`, per-key promises in Node.js, or a memoized future. This is the first-line fix: it is correct, adds no infrastructure, and converts N simultaneous rebuilds into 1.
2. **Distributed locking with short lease.** Across many instances, use `SET key lock-value NX PX 2000` in Redis (or an etcd/consul lease) so only one instance rebuilds while others briefly wait or serve stale. Always include a TTL on the lock and a randomized wait/backoff for losers — a lock without expiry turns a crashed holder into a permanent miss.
3. **Probabilistic early expiration.** Each reader independently decides to refresh early with probability that rises as the TTL approaches, spreading recomputation over time instead of synchronizing it at expiry (the classic antirez formulation: delta = expiry - now, trigger refresh with probability delta / (beta * TTL)). Combine with coalescing so the "early" winner is still a single request.
4. **Stale-while-revalidate (SWR).** Store the value with two timestamps — fresh and stale: serve fresh immediately; serve stale (past fresh, before stale limit) while exactly one background task refreshes. The cache never blocks on the origin for traffic it can serve slightly old, which removes the sawtooth entirely for tolerant data.
5. **Refresh-ahead / background warming.** A scheduled job or hook (on write, on deploy, on cron slightly before expiry) recomputes hot keys before any request misses. Simplest mental model and fully off the request path, at the cost of possibly wasted refreshes if the key stops being read.

## Implementation Patterns

1. **Per-key promise map (Node.js).** Keep a `Map<string, Promise>` of in-flight rebuilds; on miss, check the map before starting work, store the new promise, and delete it in `finally`. Guard against unbounded growth by clearing the map when the value lands or the promise settles — the entry's lifetime is one rebuild, not one TTL.
2. **singleflight.Group (Go).** Wrap the rebuild function in `group.Do(key, fn)` so the first caller executes and the rest receive the same result and error; use `Forget` after long rebuilds so a later burst does not reuse an aging in-flight result after upstream data changed.
3. **Double-timestamp cache entries.** Write entries as `{ value, freshUntil, staleUntil }`; the read path has three branches (fresh: return; stale: return + trigger one async refresh under a lock; dead: block or degrade). This one structure implements both SWR and serves as the substrate for probabilistic early refresh inside the "fresh" branch.
4. **Lock-plus-fallback read path.** Try to acquire the rebuild lock; if acquired, rebuild and publish; if not, either poll briefly for the value (bounded, e.g., 50 ms intervals up to the rebuild deadline) or serve stale/partial content. Never let non-lock-holders sleep unboundedly — that reintroduces the latency spike under a different name.
5. **Jittered TTLs everywhere.** Set TTLs with randomized spread (e.g., base TTL ± 20%) so cohort keys expiring together (written in the same request, deployed in the same warmup) do not share an expiry instant. Jitter is a one-line fix that defuses most synchronization for near-zero cost.

## Operational Considerations

1. **Measure stampede exposure before and after.** Track concurrent identical-origin-queries per key (or origin QPM spikes at TTL boundaries) as a gauge; the fix is proven when the p99 during the expiry window matches the steady-state p99, not when a code review says "should be fine".
2. **Size the stale window to data tolerance, not convenience.** Stale-while-revalidate silently trades freshness for speed; for prices, inventory, or auth data the staleUntil must be near-zero or the refresh must be synchronous. Document per key class which failure (stale data vs slow response) is preferred.
3. **Beware coalescing + per-user data.** singleflight keyed globally is correct for shared keys but wrong for per-user values where concurrent requests differ; key the promise map by the full cache key including user scoping, or you will serve one user another user's result.
4. **Handle rebuild failure explicitly.** On failure, re-serve the stale value with an extended staleUntil and emit an alert instead of deleting the entry; a stampede during a partial outage is the canonical escalation from "degraded" to "down".
5. **Pre-warm after deploys and flushes.** Trigger refresh-ahead for the top-N keys by traffic on startup (or lazily gate traffic with a readiness check that warms the hot set); combine with rolling deploys so surviving instances coalesce the load. Cold cache + full traffic is the one stampede coalescing alone cannot absorb.

## Related

api-response-caching, cache-control-headers, redis-pipeline-batching, cdn-cache-strategy, latency-budget-allocation
