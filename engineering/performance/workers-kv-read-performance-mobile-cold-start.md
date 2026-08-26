# Workers KV Read Performance and Cold-Start Behavior on Mobile

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project Workers that read feature flags, session tokens, and
rate-limit counters from KV show inconsistent latency on mobile
clients. The median KV read is 5–15 ms (cached in the local PoP),
but p95 spikes to 150–400 ms when the mobile user hits a PoP that
has not seen that key recently. Mobile users switching between
WiFi and cellular (and thus between PoPs) trigger cold KV reads
far more often than desktop users on stable connections. An
additional symptom: the first request after a Worker isolate
recycle (cold start) adds 80–200 ms regardless of KV state
because the isolate itself must be initialised before the KV
read can even begin.

## Context

Workers KV is a globally distributed, eventually consistent key-
value store. Reads are served from an in-memory cache in the
local PoP's isolate; if the key is not cached locally, KV
performs a read from the nearest storage node in the global KV
network. The in-memory cache TTL is approximately 60 seconds by
default (configurable per-read via `cacheTtl`). Mobile users on
cellular networks change PoPs frequently due to network handoffs,
effectively "busting" their per-PoP KV cache. Durable Objects
provide a strongly consistent alternative with lower read
latency for hot data (one global location vs. eventually
consistent global read), at the cost of higher write latency and
geographic lock-in. For example project the choice between KV and DO
for specific data shapes is a key latency lever.

## KV read latency breakdown

```
Scenario                         Typical latency   Notes
──────────────────────────────────────────────────────────────
KV read — PoP cache hit           1–15 ms          Isolate in-mem
KV read — PoP cache miss,         50–120 ms        Network fetch
  nearby KV storage node                           from CF KV store
KV read — PoP cache miss,         100–300 ms       Cross-region KV
  remote KV storage node                           storage hop
Worker cold start (isolate init)  80–200 ms        Added to first
                                                   request only
Worker cold start + KV miss        200–500 ms       Combined worst
                                                   case — mobile
                                                   p95 on PoP churn

Mobile PoP churn effect:
  A mobile user switching from WiFi (PoP A) to cellular (PoP B)
  will hit KV miss at PoP B for every key that was warm at PoP A.
  Desktop users on fixed connections rarely change PoP mid-session.
```

## Reading KV with explicit cacheTtl

```typescript
// env.KV_FLAGS is bound in wrangler.toml / Workers dashboard.
// Default cacheTtl is 60 s. Increase for stable config data;
// keep low (or zero) for data that changes frequently.

// Stable feature flag (changes at deploy time only):
const flagValue = await env.KV_FLAGS.get("feature:dark-mode", {
  type:     "json",
  cacheTtl: 3600,  // cache in isolate for 1 hour
});

// Rate-limit counter (needs to be fresh each check):
// DO NOT cache — use a Durable Object for this instead.
const rlKey = await env.KV_FLAGS.get(`rl:${userId}`, {
  cacheTtl: 0,  // explicit: no local cache
});
```

```
cacheTtl guidelines for example project:

  Key pattern              cacheTtl   Rationale
  ──────────────────────────────────────────────────────────
  feature:*  (flags)       3600 s     Changes on deploy only
  config:*   (app config)  1800 s     Rarely updated
  session:*  (JWT hints)   60  s      Per-session, changes on
                                      rotation
  rl:*       (rate limit)  0   s      Use Durable Object instead
  user:*     (profile)     300 s      Acceptable staleness
  hot:*      (top posts)   30  s      Feed freshness tradeoff
```

## KV vs Durable Objects for hot data

```
Use case              KV                    Durable Object
──────────────────────────────────────────────────────────────
Feature flags         Ideal — reads are     Overkill; DO has
                      eventually consistent, higher cost and
                      staleness fine         single-location
                      for flags             latency penalty

Rate limiting         Wrong — eventual       Correct — strongly
                      consistency means      consistent counter
                      counters can           with atomic increment
                      overccount under load

Session tokens        Acceptable (60 s      Only if sub-second
                      staleness tolerable)   consistency needed

User presence         Wrong — staleness      Correct — DO
                      causes ghost           maintains real-time
                      online counts          co-presence state

Top-N feed cache      Acceptable —           Overkill
                      build from KV +
                      stale-while-reval

Distributed mutex     Wrong                 Correct — Alarm API
```

```typescript
// Durable Object for rate limiting (correct pattern):
// objects/RateLimiter.ts

export class RateLimiter implements DurableObject {
  private count = 0;
  private windowStart = Date.now();

  async fetch(req: Request): Promise<Response> {
    const now = Date.now();
    // Reset window every 60 s
    if (now - this.windowStart > 60_000) {
      this.count = 0;
      this.windowStart = now;
    }
    this.count++;
    const allowed = this.count <= 100;  // 100 req / 60 s
    return new Response(JSON.stringify({ allowed, count: this.count }));
  }
}
```

## Edge cache warming strategies

```typescript
// Strategy 1: Preload KV keys during the Worker's global setup
// (runs once per isolate start; amortises cold-start + KV miss)

let flagCache: Record<string, unknown> = {};

async function warmFlagCache(env: Env): Promise<void> {
  const keys = ["feature:dark-mode", "feature:video-upload",
                 "config:feed-page-size"];
  const results = await Promise.all(
    keys.map(k => env.KV_FLAGS.get(k, { type: "json", cacheTtl: 3600 }))
  );
  keys.forEach((k, i) => { flagCache[k] = results[i]; });
}

// In the Worker handler, check in-memory before calling KV:
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext) {
    if (Object.keys(flagCache).length === 0) {
      // First request in this isolate; warm synchronously.
      // Subsequent requests in the same isolate skip this.
      await warmFlagCache(env);
    }
    const darkMode = flagCache["feature:dark-mode"] as boolean;
    // ...
  },
};
```

```typescript
// Strategy 2: Scheduled Worker pre-warms PoP caches at
// deploy time (reduces cold reads after deploys)

// wrangler.toml:
// [[triggers]]
// crons = ["*/5 * * * *"]   ← every 5 min to keep warm

export default {
  async scheduled(_event: ScheduledEvent, env: Env) {
    // Force a KV read with cacheTtl=300 so the local PoP cache
    // is warm for the next 5 minutes across all key PoPs.
    // This does not guarantee all PoPs are warm — only the
    // ones the cron runs on. Helps most-trafficked PoPs.
    const keys = ["feature:dark-mode", "config:feed-page-size"];
    await Promise.all(
      keys.map(k => env.KV_FLAGS.get(k, { cacheTtl: 300 }))
    );
  },
};
```

## Cold-start overhead: characterisation

```
Cold start triggers:
  1. First request after isolate recycle (~15-30 min idle)
  2. After Worker deployment (all isolates recycled)
  3. When Cloudflare routes to a new PoP (mobile PoP churn)
  4. After Worker CPU-time overrun (isolate killed mid-request)

Cold start time breakdown (Workers runtime, 2025 data):
  V8 isolate init:        20–60 ms  (cannot avoid)
  Global scope execution: 10–50 ms  (your top-level JS)
  First KV read (miss):   50–150 ms (cold network)
  First D1 connection:    30–80 ms  (can parallelise)

Mitigation: minimise global scope work:
  → Move heavy initialisation into the first-request path
    (lazy, guarded by a flag).
  → Use Workers Smart Placement (2024+) to co-locate the
    Worker with its D1/KV storage — reduces cold KV miss
    hop distance.
  → Keep the Worker bundle small; large bundles increase
    parse time during isolate init.
```

## Anti-patterns

- **Using KV for strongly consistent state** — KV is eventually
  consistent with up to 60 s (sometimes longer) lag between a
  write and a read at a different PoP. Rate limit counters,
  user session flags that gate access, and mutex patterns all
  require Durable Objects.
- **Setting cacheTtl=0 globally to get fresh data** — this
  converts every KV call into a network read (50–300 ms). The
  correct pattern is to use cacheTtl=0 only for data that must
  be fresh (rate limits) and push those to DOs.
- **Not parallelising KV reads** — `await env.KV.get("a")` then
  `await env.KV.get("b")` is serial. Use `Promise.all` to fan
  out: both cache misses complete in parallel at the cost of one
  RTT instead of two.
- **Warming KV in the `scheduled` handler and assuming all PoPs
  get warm** — cron runs on a subset of PoPs. Warming is best-
  effort; do not design a correctness guarantee on it.
- **Treating KV write latency as the same as read latency** —
  KV writes propagate globally in ~60 s and are not
  synchronous. Writes appear locally fast (acknowledged to the
  Writer) but distant PoPs will serve stale data for up to 60 s.

## Gotchas

- **KV isolate-local cache is per-isolate, not per-PoP** —
  Cloudflare may run multiple isolates in the same PoP.
  `cacheTtl` data is not shared between isolates; a warm read
  in isolate A does not warm isolate B in the same PoP.
  The PoP-level KV cache (below isolate) IS shared and has its
  own TTL (not directly configurable by the developer).
- **KV `list()` is always a network call** — `env.KV.list()`
  bypasses the isolate-local cache entirely. Avoid list() in
  the hot path; build an index key pointing to a serialised
  list and `get()` that index instead.
- **Workers Smart Placement may route the Worker away from the
  PoP closest to the user** — Smart Placement optimises for
  latency to storage (D1, KV). For mobile users who are
  geographically far from the storage region, this shifts
  latency from the storage hop to the device-to-Worker hop.
  Measure both before enabling.
- **KV metadata reads are faster than value reads** — if you
  only need a flag (present/absent) or a small integer,
  store it in KV metadata (`put(key, "", { metadata: flag })`)
  and read with `getWithMetadata(key)`. Metadata is returned
  with the cache hit, no extra bytes in the value body.
- **Deploying a new Worker version does not invalidate the KV
  in-memory cache** — if a flag in KV was cached for 3600 s
  and you push a hotfix that changes the flag value, the cached
  isolates will continue reading the old value for up to 1 hour.
  Use short `cacheTtl` for flags that need to update quickly on
  deploy, or store a version stamp and invalidate the in-memory
  `flagCache` map when the stamp changes.

## Verification

- Workers Analytics Engine: track KV operation latency per key
  prefix. p95 for `feature:*` reads ≤ 20 ms (confirms warm
  cache); p95 for `rl:*` reads ≥ 50 ms confirms those have
  been migrated to Durable Objects (no caching).
- Cold-start frequency measured via a `performance.now()` delta
  in global scope vs first-request handler; log to Analytics
  Engine. Target: < 0.5 % of requests are cold starts.
- `Promise.all` KV fan-out confirmed in code review: no serial
  `await kv.get()` chains in the hot path.
- Durable Object rate limiter verified consistent under load
  test (Grafana k6): 100 concurrent mobile sessions, counter
  never exceeds 100/60s per user across concurrent requests.
- KV write → read propagation time verified with a canary test:
  write a timestamp key, read it from 3 geographic probes;
  all probes converge within 60 s.

## Related

- `documentation/categories/performance/kv-read-performance.md`
- `documentation/categories/performance/cloudflare-workers-performance.md`
- `documentation/categories/performance/workers-cold-start-optimization.md`
- `documentation/categories/performance/cloudflare-cache-api-workers-mobile.md`
- `documentation/categories/database/d1-query-optimization.md`

## Source URLs (verified 2026-08-22)

- Workers KV runtime API — https://developers.cloudflare.com/kv/api/
- KV consistency model — https://developers.cloudflare.com/kv/reference/consistency/
- Durable Objects overview — https://developers.cloudflare.com/durable-objects/
- Workers Smart Placement — https://developers.cloudflare.com/workers/configuration/smart-placement/
- Workers Cold Starts (Cloudflare blog) — https://blog.cloudflare.com/eliminating-cold-starts-with-cloudflare-workers/
