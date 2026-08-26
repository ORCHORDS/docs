# Workers CPU Time Optimization: Budget, Profiling, and Mobile-First Fast Path

**Date:** 2026-08-22
**Author:** example.com
**Status:** active

## Symptom

example project Workers handling feed construction and media manifest assembly are
intermittently terminated with `Error: Worker exceeded CPU time limit`
(Workers free tier: 10 ms; paid tier: 50 ms wall-clock CPU). Even on the
paid plan, Workers that parse large JSON payloads, validate schemas, and
hydrate D1 results within a single isolate execution occasionally breach
50 ms on mobile-origin-fetch paths where cold D1 reads plus JSON processing
push aggregate CPU above the budget. Mobile clients experience 503 responses
and retries rather than graceful degradation.

## Context

Cloudflare Workers CPU time is measured differently from wall-clock time:

- **Wall-clock time**: total elapsed time the isolate is alive (up to 30 s
  on paid, unlimited with Durable Objects streams).
- **CPU time**: time the isolate's JavaScript actually executes (not including
  time awaiting I/O). This is what the 10 ms / 50 ms limit governs.

`await env.DB.all()` does not consume CPU time while waiting — the clock
stops during async I/O. CPU time is consumed by JSON parsing, schema
validation, array transformations, string operations, and cryptography. On
mobile-heavy paths where example project Workers also run device detection, response
personalization, and analytics emission, cumulative CPU easily exceeds 50 ms
if not profiled and trimmed.

## CPU time budget breakdown

```
Workers CPU time budget (Cloudflare, 2026):

  Plan                 CPU limit    Behaviour on breach
  ─────────────────────────────────────────────────────────
  Free (default)       10 ms        Worker terminated, 503 returned
  Paid (Workers Paid)  50 ms        Worker terminated, 503 returned
  Durable Objects      unlimited*   Subject to fair-use; no hard kill
  Workers for Platforms unlimited*  Per-customer limits configurable

  * Durable Objects and Workers for Platforms still have per-isolate
    CPU limits per turn (between awaits); the total across turns is
    effectively unlimited for long-lived connections.

CPU time is measured per-request (per-invocation), not cumulatively.
A Worker that averages 20 ms CPU but occasionally hits 55 ms will
breach the 50 ms limit on those spikes.
```

## Profiling with Date.now() checkpoints

```typescript
// Lightweight CPU-time profiling using Date.now().
// Date.now() measures wall-clock time, but during synchronous
// execution (between awaits) wall-clock ≈ CPU time.
// Use this to identify which phase consumes the most CPU.

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const t0 = Date.now();

    // Phase 1: request parsing + device detection
    const ctx  = parseRequest(req);          // sync
    const t1   = Date.now();

    // Phase 2: D1 read (I/O — clock pauses here in CPU accounting)
    const rows = await env.DB.prepare(
      `SELECT * FROM posts WHERE feed_id = ?1 LIMIT 20`
    ).bind(ctx.feedId).all();
    const t2 = Date.now();

    // Phase 3: JSON transform + schema hydration (sync, CPU-intensive)
    const feed = hydrateFeed(rows.results);  // sync
    const t3   = Date.now();

    // Phase 4: response serialization
    const body = JSON.stringify(feed);       // sync
    const t4   = Date.now();

    // Emit timing to Analytics Engine for aggregation
    env.AE.writeDataPoint({
      blobs:   ["feed", ctx.deviceType],
      doubles: [t1 - t0, t3 - t2, t4 - t3],   // parse, hydrate, serialize ms
    });

    return new Response(body, { headers: { "Content-Type": "application/json" } });
  },
};

// Interpret: t3-t2 (hydration) is the dominant CPU phase →
// optimize hydrateFeed() first.
```

```
Sample profiling output for example project feed Worker (20 posts):

  Phase                   Avg CPU (ms)   P95 CPU (ms)   Target
  ──────────────────────────────────────────────────────────────
  Request parse            0.4            0.9            ≤ 1
  D1 await (I/O, excluded) 22.0          —              N/A
  Feed hydration           18.5           31.2           ≤ 10
  JSON.stringify           3.1            5.8            ≤ 5
  Response headers         0.3            0.6            ≤ 1
  ──────────────────────────────────────────────────────────────
  Total CPU                22.3           38.5           ≤ 50

  Feed hydration is the hot path — reduce schema validation cost.
```

## JSON parse optimization

```typescript
// Anti-pattern: deserializing a large R2 JSON blob and re-serializing
// parts of it every request.  If the blob is served as-is to the client,
// pipe it through without parse.

// Slow: parse → select fields → re-serialize (CPU: 8–15 ms for 100 KB JSON)
async function manifestSlow(key: string, env: Env): Promise<Response> {
  const obj  = await env.R2_MEDIA.get(key);
  const text = await obj!.text();
  const data = JSON.parse(text);                       // 8–15 ms CPU
  const slim = { tracks: data.tracks, meta: data.meta }; // field select
  return new Response(JSON.stringify(slim));           // re-serialize
}

// Fast: if the full blob is acceptable, stream it directly
async function manifestFast(key: string, env: Env): Promise<Response> {
  const obj = await env.R2_MEDIA.get(key);
  // obj.body is a ReadableStream — no parse, no serialize, ~0 ms CPU
  return new Response(obj!.body, {
    headers: { "Content-Type": "application/json" },
  });
}

// When field selection IS needed, use a targeted regex or
// JSON.parse only on the minimal needed path:
async function manifestSelected(key: string, env: Env): Promise<Response> {
  const obj  = await env.R2_MEDIA.get(key);
  const text = await obj!.text();
  // Parse once; avoid re-serializing large nested arrays
  const { tracks, meta } = JSON.parse(text) as Manifest;
  const slim = JSON.stringify({ tracks: tracks.slice(0, 5), meta });
  return new Response(slim, { headers: { "Content-Type": "application/json" } });
}
```

## Lazy KV reads: skip the read if the cache layer already served it

```typescript
// KV reads (env.KV.get()) consume both I/O wait time and a small
// amount of CPU for deserialization.  If the response is cache-hit
// at the CDN layer, the Worker may not be invoked at all — but if
// it is invoked, avoid redundant KV reads on paths that do not
// need the stored value.

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // Mobile fast-path: static asset requests never need KV feature flags.
    // Check early and return before touching KV.
    if (url.pathname.startsWith("/static/")) {
      return fetch(req);  // pass through to CDN; no KV read
    }

    // Only read feature flags when they will be used.
    // Bad: const flags = await env.KV_FLAGS.get("flags", "json");  // always
    // Good: defer until after auth check determines the request type.
    const isAuthed = req.headers.get("Authorization") !== null;
    if (!isAuthed) {
      // Anonymous feed: no personalisation, no KV read needed
      return buildPublicFeed(req, env);
    }

    // Authed path only: read feature flags (one KV read, lazily)
    const flags = await env.KV_FLAGS.get<Flags>("flags", "json");
    return buildPersonalisedFeed(req, env, flags);
  },
};
```

## Mobile-first fast path

```typescript
// Mobile clients receive a slimmer response to reduce both Worker CPU
// (less to serialize) and mobile bandwidth.  Detect early and branch.

function isMobile(req: Request): boolean {
  const cf = (req as any).cf;                  // Cloudflare request metadata
  return cf?.deviceType === "mobile" || cf?.deviceType === "tablet";
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const mobile = isMobile(req);

    // Mobile fast path: fewer posts, no waveform data, compressed JSON
    if (mobile) {
      const rows = await env.DB.prepare(
        `SELECT p.id, p.title, p.cover_key, u.display_name
         FROM   posts p JOIN users u ON u.id = p.user_id
         WHERE  p.feed_id = ?1 AND p.created_at < ?2
         ORDER  BY p.created_at DESC LIMIT 10`    // 10 instead of 20
      ).bind(feedId, cursor).all();

      // Minimal JSON — no waveform, no full metadata
      const payload = rows.results.map(r => ({
        id:     r.id,
        title:  r.title,
        cover:  `https://media.example.com/${r.cover_key}?width=320&format=avif`,
        author: r.display_name,
      }));

      return new Response(JSON.stringify(payload), {
        headers: {
          "Content-Type": "application/json",
          "Content-Encoding": "identity",   // brotli applied by CF edge
        },
      });
    }

    // Desktop path: full 20-post payload with waveform data
    return buildDesktopFeed(req, env);
  },
};
```

```
CPU time impact of mobile fast-path branching (example project feed Worker):

  Path             Posts   Fields/post   hydration CPU   serialize CPU
  ──────────────────────────────────────────────────────────────────────
  Desktop (full)     20       12            18.5 ms         5.1 ms
  Mobile (slim)      10        4             4.2 ms          1.3 ms

  Mobile CPU reduction: 77 % — well within 50 ms budget even with
  other processing phases included.
```

## Anti-patterns

- **Schema validation with a full JSON Schema library on every request** —
  libraries like Zod or Ajv add 5–20 ms CPU per invocation when validating
  complex schemas; validate at build time or write targeted checks for the
  5–10 fields that actually need runtime validation.
- **Awaiting multiple KV reads in sequence** — each `await env.KV.get()` is
  a separate I/O round-trip but deserialization is synchronous CPU; batch or
  skip reads not needed on the hot path.
- **Date.now() profiling in production without sampling** — writing an
  Analytics Engine data point on every request adds ~0.2 ms CPU and one
  network write; gate on a 1-in-100 sample (`Math.random() < 0.01`) in
  production.
- **Logging large objects with JSON.stringify for debug** — `console.log(largeObj)`
  serializes the object even in production unless stripped at build time;
  use structured logging with field selection.
- **Running crypto operations synchronously** — `crypto.subtle.digest()` is
  async but the underlying hash is CPU-bound; prefer content-addressed keys
  computed at upload time over per-request hashing.

## Gotchas

- **CPU time does not include time awaiting I/O** — `await fetch()` and
  `await env.DB.all()` do not burn CPU budget; only synchronous execution
  between awaits does. Profiling with `Date.now()` around awaits will show
  wall-clock including I/O; subtract to get CPU-only estimates.
- **`ctx.waitUntil()` CPU is charged after response** — background work
  registered with `waitUntil` continues after the response is sent and
  consumes additional CPU time counted against the same budget; heavy
  background processing can still cause termination.
- **Cold start does not count against CPU budget** — isolate initialization
  time (module evaluation, global scope) is not counted; only handler
  execution is. But cold-start JS evaluation does affect wall-clock TTFB.
- **Free plan 10 ms limit is strict** — even a single `JSON.parse` of a
  100 KB string can exceed 10 ms on the free plan; paid plan is the minimum
  for example project production Workers.
- **Workers AI and Vectorize bindings consume CPU** — embedding lookups via
  Workers AI add ~5–15 ms CPU beyond the I/O wait; account for this in the
  50 ms budget if using AI features in the feed path.

## Verification

- Workers dashboard → "CPU Time" metric shows P50/P95/P99 distribution per
  Worker; alert if P99 exceeds 40 ms (leaving 10 ms margin).
- Date.now() checkpoint instrumentation (1 % sample) in Analytics Engine;
  query per-phase median and P95 CPU to identify the hot phase.
- Deploy to staging with `wrangler dev --remote` and use `--inspect` to
  connect Chrome DevTools for V8 CPU profiling of the Worker handler.
- Confirm mobile fast path activates: assert response body contains 10 posts
  (not 20) when `CF-Device-Type: mobile` header is set on the test request.
- Load test with k6 at 200 RPS; watch for any 503 `CPU time exceeded` errors
  in Workers logs (Logpush `Outcome: exception`).

## Related

- `documentation/docs/policies/performance/workers-cold-start-optimization.md`
- `documentation/docs/policies/performance/workers-cpu-profiling.md`
- `documentation/docs/policies/performance/kv-read-performance.md`
- `documentation/docs/policies/performance/cloudflare-workers-performance.md`
- `documentation/docs/policies/performance/workers-kv-read-performance-mobile-cold-start.md`

## Sources

- Cloudflare Workers Limits — https://developers.cloudflare.com/workers/platform/limits/
- Workers CPU Time (docs) — https://developers.cloudflare.com/workers/observability/metrics-and-analytics/
- Workers Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Workers: waitUntil — https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- V8 CPU profiling via wrangler dev — https://developers.cloudflare.com/workers/observability/dev-tools/cpu-profiler/
