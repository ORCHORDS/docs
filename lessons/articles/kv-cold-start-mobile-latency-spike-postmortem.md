# KV Cold-Start Latency Spike Causing Inconsistent State on Mobile

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Mobile users of the example project anonymous social platform experienced a degraded feed during a 22-minute window following a scheduled Workers deploy. Newly posted content appeared in some sessions but not others, and toggling the feed refresh produced flickering between old and new state. Backend error rates remained at zero, making the incident invisible to standard alerting. User reports surfaced the issue via the in-app feedback channel before any monitor fired.

## Context

example project's feed delivery is served by a `FeedWorker` that reads a ranked post list from Workers KV (`example project-feed-cache` namespace). The KV store is populated by a background `RankingWorker` that runs on a Cloudflare Cron Trigger every 60 seconds. Feed keys are written with a TTL of 120 seconds and a `Cache-Control: max-age=60` header set on KV metadata, which the CDN layer respects.

At the time of the incident, the mobile client (React Native, iOS and Android) had a 30-second background refresh polling the `/feed` endpoint. The Workers deploy (`v1.94.0`) restarted all `FeedWorker` isolates across Cloudflare's edge. On cold start, each isolate's in-memory cache was empty. The isolates fell through to KV reads, but KV's eventual consistency model meant that some edge nodes had not yet received the most recent write from `RankingWorker`. Mobile clients sitting on those edge nodes received stale feed data from KV, while clients on other edges received fresh data.

The 120-second TTL on KV entries meant stale reads could persist for up to 2 minutes per cache key before the next `RankingWorker` write propagated. With 30-second client polling, some mobile users cycled between stale and fresh responses on consecutive requests as their connections load-balanced across edges.

## Timeline

- **09:15 UTC** — `v1.94.0` deploy completes. All `FeedWorker` isolates restart.
- **09:15–09:17 UTC** — Cold-start window: all isolates fall through to KV. KV reads succeed but return values that may be up to 2 minutes stale depending on edge replication lag.
- **09:18 UTC** — First user feedback report: "my feed keeps jumping between old and new posts."
- **09:22 UTC** — Three more reports. On-call checks Workers Analytics — error rate 0%, P99 latency normal. No alert has fired.
- **09:24 UTC** — On-call tails `FeedWorker` logs. Notices KV read hits with `age` metadata values up to 118 seconds — just under TTL.
- **09:27 UTC** — On-call correlates deploy timestamp with report timestamps. Identifies cold-start as the trigger.
- **09:31 UTC** — Decision: purge affected KV keys and force a `RankingWorker` cron invocation via `wrangler trigger`.
- **09:35 UTC** — `RankingWorker` invocation completes. KV keys refreshed globally.
- **09:37 UTC** — User reports stop. Feed consistency confirmed across multiple test devices on different network carriers.
- **09:45 UTC** — Incident closed. Post-mortem scheduled.

## Root Cause

Workers KV is **eventually consistent** — writes propagate to all edge nodes within approximately 60 seconds under normal conditions, but the propagation window is not bounded by a hard SLA. The `FeedWorker`'s design assumed that a KV read would always return a value no older than the key's TTL. This assumption is wrong: a KV write that has not yet propagated to an edge node means the node returns the previous value (still within TTL at that edge) rather than the newest write.

The specific failure chain was:

1. `RankingWorker` writes a new feed ranking at 09:14:50 UTC.
2. The write propagates to ~80% of edge nodes within 30 seconds, but a subset of European edge locations lag by 60–90 seconds.
3. `FeedWorker` isolates restart globally at 09:15 UTC. European isolates, with empty in-memory caches, read from their local KV store — which has not yet received the 09:14:50 write.
4. European mobile clients receive the previous ranking (09:13:50 write), while US clients receive the 09:14:50 write.
5. Mobile clients using Cloudflare's anycast routing occasionally flip between edge regions across requests, producing the observed flickering.

The `Cache-Control` header mismatch (KV TTL 120s vs cache header 60s) meant the CDN layer sometimes served an even older cached copy from its own layer, adding a third inconsistent state.

## Fix / Resolution: Cache API as Primary, KV as Fallback

The fix inverts the caching hierarchy. The Cloudflare Cache API (available to Workers via `caches.default`) provides per-edge, per-isolate cache with explicit `stale-while-revalidate` semantics. KV becomes the fallback for Cache API misses rather than the primary store. This eliminates the KV consistency window from the hot read path.

```typescript
// workers/feed-worker.ts

const FEED_CACHE_KEY = "https://internal.example project/feed/v1/ranked";
const CACHE_TTL_SECONDS = 55; // slightly under RankingWorker 60s interval
const KV_TTL_SECONDS = 120;

export interface Env {
  FEED_CACHE: KVNamespace;
  FEED_VERSION: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;
    const cacheKey = new Request(FEED_CACHE_KEY);

    // 1. Try Cache API first — this is per-edge and consistent within the edge
    const cached = await cache.match(cacheKey);
    if (cached) {
      const age = Date.now() - Number(cached.headers.get("x-feed-written-at") ?? 0);
      // Serve from Cache API if fresh enough; trigger background revalidation if stale
      if (age < CACHE_TTL_SECONDS * 1000) {
        return buildFeedResponse(cached, "cache-api-hit");
      }
      // stale-while-revalidate: serve stale immediately, refresh in background
      ctx.waitUntil(revalidateFeed(env, cache, cacheKey));
      return buildFeedResponse(cached, "cache-api-stale");
    }

    // 2. Cache API miss — fall through to KV (accepts eventual consistency lag)
    const kvValue = await env.FEED_CACHE.getWithMetadata<FeedMetadata>("feed:ranked:v1", {
      type: "json",
    });

    if (kvValue.value) {
      const response = buildFeedResponseFromKV(kvValue, "kv-hit");
      // Populate Cache API so subsequent requests on this edge skip KV
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
      return response;
    }

    // 3. Hard miss — return empty feed with short retry header
    return new Response(JSON.stringify({ posts: [], source: "miss" }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
        "Retry-After": "5",
        "x-feed-source": "miss",
      },
    });
  },
};

async function revalidateFeed(
  env: Env,
  cache: Cache,
  cacheKey: Request,
): Promise<void> {
  const kvValue = await env.FEED_CACHE.getWithMetadata<FeedMetadata>("feed:ranked:v1", {
    type: "json",
  });
  if (kvValue.value) {
    const response = buildFeedResponseFromKV(kvValue, "kv-revalidation");
    await cache.put(cacheKey, response);
  }
}

type FeedMetadata = { writtenAt: number; version: string };

function buildFeedResponse(response: Response, source: string): Response {
  const r = new Response(response.body, response);
  r.headers.set("x-feed-source", source);
  return r;
}

function buildFeedResponseFromKV(
  kv: KVNamespaceGetWithMetadataResult<unknown, FeedMetadata>,
  source: string,
): Response {
  return new Response(JSON.stringify(kv.value), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}, stale-while-revalidate=30`,
      "x-feed-written-at": String(kv.metadata?.writtenAt ?? 0),
      "x-feed-source": source,
    },
  });
}
```

## Prevention Checklist

- [ ] Align KV TTL and `Cache-Control` `max-age` values — they should be set together in a single constant, never independently
- [ ] Add `x-feed-source` and `x-feed-written-at` headers to all feed responses; log them in Workers Analytics so KV lag is always visible
- [ ] Alert on P95 KV read `age` exceeding 90 seconds (50% beyond the `RankingWorker` write interval)
- [ ] Instrument cold-start events explicitly: log a `cold_start: true` field on the first request to each isolate and track the cold-start rate after every deploy
- [ ] Add a post-deploy smoke test that reads the feed from at least 3 geographic Cloudflare PoPs and asserts that the `x-feed-written-at` values are within 30 seconds of each other
- [ ] Document the Cache API → KV fallback pattern as the team standard for low-latency, high-consistency reads

## Monitoring Gaps Identified

- No metric tracked KV value `age` at read time — the team only knew KV reads succeeded, not how stale the returned values were
- No deploy-correlated monitor: after every Worker deploy there was no automatic check for elevated user-facing inconsistency or session-level divergence in API responses

## Anti-patterns

- Using Workers KV as a real-time consistency store — KV is a globally distributed, eventually consistent store with a propagation delay; treating it like a strongly consistent database causes race conditions after writes and cold starts
- Setting KV TTL and `Cache-Control` `max-age` independently — when these values diverge, the CDN and KV can serve responses from different generations of data, creating a multi-layer inconsistency that is extremely hard to debug from client-side reports alone

## Gotchas

- Workers KV `get` on a cold isolate returns the value held at the nearest KV node, which may not yet have the latest write — this is not an error and will not surface in error rate metrics; it is silent stale data
- Cloudflare's anycast routing can cause consecutive requests from the same mobile client to hit different edge PoPs (especially true on mobile networks with frequent IP changes), meaning stale/fresh inconsistency can alternate on every poll cycle

## Verification

```bash
# Check feed response headers from multiple PoPs using Cloudflare's cf-ray header
for region in sfo lhr nrt; do
  curl -s -o /dev/null -D - \
    "https://example project.workers.dev/feed" \
    -H "cf-connecting-ip: 1.1.1.1" \
    | grep -E "x-feed-source|x-feed-written-at|cf-ray|age"
  echo "---"
done

# Trigger a forced RankingWorker run and verify KV propagation
wrangler cron trigger ranking-worker --env production

# Monitor KV write propagation lag via Workers Analytics Engine
wrangler analytics --dataset feed_kv_age --filter 'age > 90' --tail
```

## Related

- `lessons/cache-cold-start-avalanche.md`
- `lessons/eventual-consistency-surprises-clients.md`
- `lessons/kv-read-costs-capacity-planning-retrospective.md`
- `lessons/cache-invalidation-is-harder-than-caching.md`

## Sources

- https://developers.cloudflare.com/kv/reference/consistency/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
