# KV Edge Cache Warming: Mobile First-Request Latency

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A mobile user in Southeast Asia opens the app cold — first
session of the day, new PoP, no prior traffic from that
region. The anonymous session token check, feature flag
reads, and content feed key all miss the edge cache and
fall through to KV central storage. Perceived time-to-
first-content is 400–800 ms instead of the sub-100 ms
target. Repeat users in the same city see < 5 ms. The
spike is invisible in aggregate p50/p95 — it only appears
in new-session or regional cold-boot cohorts.

## Context

example project stores three categories in KV: anonymous session
tokens (short-lived, per-device), feature flags (read-
heavy, updated infrequently), and content feeds (JSON
blobs recomputed on Worker). KV is optimised for high-
read, low-write workloads. At steady state a warm PoP is
fast. The problem is the warming window: KV's eventual
consistency means a newly written key takes up to 60 s to
propagate globally, and an uncached key at a cold PoP
must climb the full read hierarchy on the first request.

## KV Consistency Model and the 60-Second Window

KV uses hybrid push/pull replication. A write is visible
at the originating PoP immediately (read-your-own-write
within the same PoP). Other PoPs learn via triggered push
or lazy pull on next read miss.

```
Write committed at CF edge (origin PoP)
  ├─ same PoP:    visible immediately (RYOW guaranteed)
  ├─ nearby PoPs: seconds  (push triggers flush)
  └─ global PoPs: up to 60 s (cache TTL expiry + pull)
```

Negative lookups (key not found) are cached with the same
TTL. A key written after a PoP cached a negative result
stays null until that entry expires — a second 60 s window
stacked on top of the first. For example project: a feature flag
written 30 s ago may not be visible at a cold PoP.

## KV Read Latency Tiers

```
Tier          Location         Typical latency
----------------------------------------------
L0: in-PoP   edge memory      < 1 ms  (hot keys)
L1: regional  tiered KV cache  5–20 ms
L2: central   KV storage proxy 50–200 ms
```

**L0:** Cloudflare's 2025 KV rollout added in-memory
caching for the hottest keys. Over 40 % of global KV
requests now resolve in < 1 ms (< 0.03 % of keys drive
this traffic). **L1:** Tiered cache resolves ~30 % of
misses without a central trip; P99 reads to KVSP are
below 5 ms. **L2:** A true cold read on a transoceanic
Worker invocation reaches 150–200 ms end-to-end.

## Workers Cache API as L1 in Front of KV

The Cache API is PoP-local. A `cache.put()` stores a
Response in the executing data center; subsequent requests
to that PoP `cache.match()` and bypass KV entirely. This
is the **write-on-read** warming pattern:

```typescript
const CACHE = "kv-l1";

async function kvWithL1<T>(
  kv: KVNamespace,
  key: string,
  l1TtlSec: number,
): Promise<T | null> {
  const cache  = await caches.open(CACHE);
  const cKey   = new Request(`https://kv.local/${key}`);

  const hit = await cache.match(cKey);          // L1
  if (hit) return hit.json() as Promise<T>;

  const value = await kv.get<T>(key, "json");   // KV
  if (value === null) return null;

  await cache.put(                              // warm L1
    cKey,
    new Response(JSON.stringify(value), {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": `max-age=${l1TtlSec}`,
      },
    }),
  );
  return value;
}
```

Cache API entries are ephemeral and PoP-local — they do
not replicate and are evicted under memory pressure. Each
PoP warms itself from its own first request per key.

## Short-TTL vs Long-TTL Trade-off

L1 TTL must always be ≤ KV TTL to avoid serving a value
that KV has already expired.

```
Data class           KV TTL   L1 TTL   Notes
-------------------------------------------------
Feature flags        3600 s   300 s    High PoP reuse
Content feed          600 s    60 s    Moderate reuse
Anon session token    900 s     —      Skip L1 (1:1)
Expensive recompute  86400 s  600 s    Pair with Cron
```

For values expensive to recompute, use a long KV TTL and
a moderate L1 TTL so stale values reach all PoPs within
minutes. Pair KV TTLs > 24 h with a Cron Worker that
periodically re-validates and re-writes — a bad write
otherwise persists globally for the full TTL.

## KV Namespace Migration Strategies

KV has no native copy API. Moving across environments
requires a dual-write phase:

1. Deploy with dual-write: writes go to both old and new
   namespace simultaneously.
2. Run a backfill Cron Worker (old → new); use
   `ctx.waitUntil()` to avoid CPU time limits on large
   namespaces.
3. Verify new namespace key count matches old.
4. Switch reads to the new namespace binding; monitor
   for one propagation window (60 s).
5. Remove old namespace binding and dual-write code.

Verify that copied keys have unexpired `expiration`
timestamps (Unix epoch seconds) — lapsed TTLs expire
the destination key on arrival.

## When Durable Objects Fit Better

KV's 60 s eventual consistency is a hard constraint — it
cannot be relaxed per-namespace or per-key.

```
Use case                    KV      Durable Objects
---------------------------------------------------
Feature flags (read-heavy)  Yes     No
Anon session token          Yes     No
Rate-limit counter          No      Yes (atomic)
Real-time presence          No      Yes (strong)
Cart / inventory count      No      Yes (strong)
Feed personalisation state  Yes     No (stale OK)
```

Durable Objects offer strong consistency within a single
DO instance, atomic increments, and in-memory state that
avoids storage round-trips. For example project: any state that
changes more than once per 60 s and must be read fresh
(rate limit tokens, notification counts) belongs in a
Durable Object, not KV.

## Anti-patterns

- **Expecting cross-region consistency for KV session
  tokens.** Auth Worker in Frankfurt writes the token;
  Singapore PoP returns null for up to 60 s. Use a
  signed JWT validated locally instead.

- **Caching per-device tokens in Cache API L1.** L1 is
  PoP-local; per-device keys are not shared across users,
  so L1 hit rates approach 0 % for session tokens.

- **Setting L1 TTL longer than KV TTL.** The Cache API
  serves the value after KV has deleted it.

- **Using KV for per-request counters.** The 1 write/s
  per-key limit and 60 s propagation make KV unsuitable
  for write-heavy real-time state.

## Gotchas

- `cache.delete()` is local to the calling PoP only.
  To invalidate L1 everywhere: let TTL expire or rotate
  the cache key (e.g. `kv.local/${key}?v=${version}`).

- KV `list()` is eventually consistent — new keys may
  not appear for up to 60 s after a write.

- `cache.put()` is not compatible with tiered caching;
  use `fetch()` if you need tiered propagation.

- Always `await cache.put()` — fire-and-forget silently
  skips warming and the next request still misses L1.

## Verification

```bash
# Confirm the key exists in KV
wrangler kv key get "flag:dark-mode" \
  --namespace-id $FEATURE_FLAGS_NS_ID

# Measure cold vs warm latency from an APAC host
# Worker should set: res.headers.set("x-cache", "HIT"|"MISS")
for i in 1 2 3; do
  curl -sw "%{time_total}\n" -o /dev/null \
    -H "x-debug: 1" https://api.example.com/api/flags
done
# Expected: first ~150-200 ms (MISS), rest < 5 ms (HIT)

curl -sI https://api.example.com/api/flags | grep x-cache
# Expected on repeat: x-cache: HIT
```

A persistent `x-cache: MISS` on repeat calls in the same
region points to an un-awaited `cache.put()`.

## Related

- `cloudflare/kv-best-practices.md` — key design, TTL
  strategy, and cost model
- `cloudflare/kv-eventually-consistent.md` — consistency
  model and when to use D1 instead
- `cloudflare/kv-namespace-migration.md` — zero-downtime
  migration procedure and backfill Worker
- `cloudflare/workers-cache-api.md` — Cache API runtime
  reference and PoP-local semantics
- `cloudflare/durable-objects-best-practices.md` — when
  to replace KV with Durable Objects

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/kv/concepts/how-kv-works/
- https://blog.cloudflare.com/faster-workers-kv/
- https://blog.cloudflare.com/rearchitecting-workers-kv-for-redundancy/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/kv/reference/faq/
- https://developers.cloudflare.com/durable-objects/
