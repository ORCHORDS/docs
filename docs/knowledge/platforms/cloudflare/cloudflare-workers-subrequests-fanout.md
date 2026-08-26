# Cloudflare Workers — `waitUntil` + Subrequest Fan-out, CPU Budget, Fetch Concurrency & Mobile Payloads

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) Workers API routes need to fan out to multiple downstream services (D1, R2, Analytics Engine, an external audio CDN) in response to a single client request. Engineers see CPU limit errors, subrequest count exhaustion, and response-time regressions when all fetches are serialised. Mobile clients receive the same heavy JSON payloads as desktop and suffer unnecessary data transfer. The team needs a reliable pattern for concurrent subrequests, post-response work, and lightweight vs full payload branching.

## Context

Workers run in a V8 isolate with the following hard limits:

| Resource | Paid (default) | Notes |
|---|---|---|
| CPU time per invocation | 30 s (configurable up to 5 min with Configurable Limits) | Idle wait (fetch I/O) does NOT count toward CPU time |
| Subrequests per invocation | 1 000 | fetch() calls, including KV/D1/R2 bindings |
| Concurrent subrequests | Unlimited (practical ~6 at the TCP level) | Cloudflare recommends `Promise.all` up to ~50 |
| Wall-clock time | 30 s (Paid), 10 ms CPU on Free | Includes I/O wait |
| `waitUntil` duration | 30 s after response returned | CPU still counts |

Subrequest fan-out = firing multiple `fetch()` / binding calls concurrently with `Promise.all` or `Promise.allSettled`, rather than sequentially. This is the primary tool for reducing wall-clock latency.

## Sequential vs Concurrent — Latency Impact

Sequential (bad for example project):

```typescript
// Sequential: 3 × ~50ms = ~150ms minimum
const userRow   = await env.DB.prepare("SELECT * FROM users WHERE id=?").bind(userId).first();
const recording = await env.DB.prepare("SELECT * FROM recordings WHERE id=?").bind(recId).first();
const signedUrl = await env.R2.get(`audio/${recId}.mp3`); // binding call
```

Concurrent with `Promise.all` (correct):

```typescript
// Concurrent: max(~50ms, ~50ms, ~80ms) = ~80ms
const [userRow, recording, r2Object] = await Promise.all([
  env.DB.prepare("SELECT * FROM users WHERE id=?").bind(userId).first(),
  env.DB.prepare("SELECT * FROM recordings WHERE id=?").bind(recId).first(),
  env.R2.get(`audio/${recId}.mp3`),
]);
```

For operations where you can tolerate partial failure, use `Promise.allSettled`:

```typescript
const results = await Promise.allSettled([
  fetchAudioCDNMeta(recId),
  fetchWaveformData(recId, env),
  fetchTranscript(recId, env),
]);

// Filter fulfilled results; log rejected ones
const [cdnMeta, waveform, transcript] = results.map(r =>
  r.status === "fulfilled" ? r.value : null
);
```

## Mobile vs Desktop Payload Branching

example project API routes use the `CF-Device-Type` header to return lightweight payloads to mobile clients, reducing transfer size and parse time on constrained devices.

```typescript
interface RecordingFull {
  id: string;
  title: string;
  durationMs: number;
  waveformData: number[];      // ~50 KB
  transcript: string;          // ~100 KB
  chapters: Chapter[];
  relatedRecordings: Recording[];
  analyticsMetrics: Record<string, number>;
}

interface RecordingMobile {
  id: string;
  title: string;
  durationMs: number;
  // waveformData omitted — mobile app renders a simplified bar graph
  // transcript omitted — lazy loaded on demand
}

export async function getRecording(c: Context<{ Bindings: Env }>) {
  const recId = c.req.param("id");
  const deviceType = detectDevice(c.req.raw);
  const isMobile = deviceType === "mobile";

  // Always fetch the core row
  const corePromise = c.env.DB
    .prepare("SELECT id, title, duration_ms FROM recordings WHERE id=?")
    .bind(recId)
    .first<{ id: string; title: string; duration_ms: number }>();

  if (isMobile) {
    // Mobile: only the core row — single subrequest
    const core = await corePromise;
    if (!core) return c.json({ error: "Not found" }, 404);
    return c.json({
      id: core.id,
      title: core.title,
      durationMs: core.duration_ms,
    } satisfies RecordingMobile);
  }

  // Desktop: fan out for full payload
  const [core, waveform, transcript] = await Promise.all([
    corePromise,
    fetchWaveformFromR2(recId, c.env),
    fetchTranscriptFromR2(recId, c.env),
  ]);

  if (!core) return c.json({ error: "Not found" }, 404);

  return c.json({
    id: core.id,
    title: core.title,
    durationMs: core.duration_ms,
    waveformData: waveform ?? [],
    transcript: transcript ?? "",
  } satisfies RecordingFull);
}
```

Payload size comparison:

| Field | Mobile (bytes) | Desktop (bytes) |
|---|---|---|
| Core JSON | ~150 | ~150 |
| waveformData | — | ~51 200 |
| transcript | — | ~102 400 |
| Total | ~150 | ~153 750 |
| Subrequests | 1 | 3 |

## `waitUntil` — Post-Response Background Work

`waitUntil` extends the Worker's lifetime after `Response` is returned. Use it for non-blocking work that the client doesn't need to wait for:

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const recId = new URL(request.url).searchParams.get("id") ?? "";

    // Build response synchronously or with minimal awaiting
    const core = await env.DB
      .prepare("SELECT id, title FROM recordings WHERE id=?")
      .bind(recId)
      .first();

    const response = core
      ? Response.json(core)
      : new Response("Not found", { status: 404 });

    // After response is determined, kick off analytics and cache warming
    // These run concurrently after the response is sent to the client
    ctx.waitUntil(
      Promise.all([
        recordAnalytics(request, env, core),   // AE writeDataPoint
        warmRelatedCache(recId, env),           // pre-fetch related recordings into KV
      ])
    );

    return response;
  },
};
```

`waitUntil` rules:

| Rule | Detail |
|---|---|
| CPU counts | CPU time used inside `waitUntil` still counts toward the invocation limit |
| Duration | Up to 30 s wall-clock after response returns |
| Failures | Uncaught errors inside `waitUntil` are silently swallowed; wrap in try/catch |
| Subrequest count | Subrequests inside `waitUntil` count toward the 1 000 per-invocation limit |
| Response not delayed | `return response` happens before `waitUntil` tasks complete |

```typescript
async function recordAnalytics(
  request: Request,
  env: Env,
  core: unknown
): Promise<void> {
  try {
    env.AE.writeDataPoint({
      blobs: [new URL(request.url).pathname, detectDevice(request)],
      doubles: [1],
    });
  } catch {
    // Never let analytics failures propagate
  }
}
```

## Subrequest Budget Management

With 1 000 subrequests per invocation, example project's routes are well within limits for normal operation. Budget risks appear in:

1. **Loops over D1 results** — fetching related items per-row in a loop:

```typescript
// BAD: N+1 pattern — 1 query + N R2 fetches
const rows = await env.DB.prepare("SELECT id FROM recordings LIMIT 50").all();
for (const row of rows.results) {
  const obj = await env.R2.get(`audio/${row.id}.mp3`); // 50 subrequests
}

// GOOD: fetch concurrently and cap concurrency
const CONCURRENCY = 10;
async function batchFetch(ids: string[], env: Env) {
  const results = [];
  for (let i = 0; i < ids.length; i += CONCURRENCY) {
    const batch = ids.slice(i, i + CONCURRENCY);
    const fetched = await Promise.all(
      batch.map(id => env.R2.get(`audio/${id}.mp3`))
    );
    results.push(...fetched);
  }
  return results;
}
```

2. **Recursive fan-out** — a Worker that calls a Worker that calls another Worker via service bindings. Each hop uses subrequest budget. Keep fan-out depth ≤ 3 hops.

Subrequest budget table:

| Operation | Subrequest cost |
|---|---|
| `fetch()` to external URL | 1 |
| KV `get` / `put` | 1 |
| D1 `prepare().first()` | 1 |
| D1 batch (`exec()`) | 1 (single round-trip) |
| R2 `get` / `put` | 1 |
| Analytics Engine `writeDataPoint` | 0 (batched internally) |
| Service binding call | 1 |
| Durable Object `fetch` | 1 |

## CPU Time vs Wall-Clock Time

CPU time does NOT include waiting for I/O. A Worker that does 100 ms of I/O (fetch, D1, R2) and 2 ms of JavaScript computation uses only ~2 ms of CPU time. This means fan-out patterns are CPU-cheap even when wall-clock latency is high.

When to worry about CPU:
- JSON parsing of very large payloads (> 1 MB)
- Cryptographic operations (PBKDF2, AES-GCM on large buffers)
- Image processing with Workers AI or Canvas API
- Loop-heavy data transformation (sorting 10 000 rows in JS)

Profile CPU usage by checking `cf-ray` headers and Logpush `cpuTime` field.

## Fan-out Pattern for Audio Delivery Route

example project's `/api/recordings/:id/stream` route fans out to build a pre-signed play response:

```typescript
export async function streamRecording(c: Context<{ Bindings: Env }>) {
  const recId = c.req.param("id");
  const userId = c.get("userId"); // from auth middleware
  const isMobile = detectDevice(c.req.raw) === "mobile";

  // Fan out: auth check, recording meta, signed URL — all concurrent
  const [authRow, recording, signedUrl] = await Promise.all([
    c.env.DB.prepare(
      "SELECT 1 FROM user_recordings WHERE user_id=? AND recording_id=?"
    ).bind(userId, recId).first(),

    c.env.DB.prepare(
      "SELECT id, title, duration_ms, file_key FROM recordings WHERE id=?"
    ).bind(recId).first<RecordingRow>(),

    generateSignedR2Url(recId, c.env, isMobile ? 300 : 3600), // shorter TTL for mobile
  ]);

  if (!authRow) return c.json({ error: "Forbidden" }, 403);
  if (!recording) return c.json({ error: "Not found" }, 404);

  // Post-response: log play event (mobile gets lightweight log)
  c.executionCtx.waitUntil(
    logPlayEvent(recId, userId, isMobile, c.env)
  );

  return c.json({ url: signedUrl, title: recording.title, durationMs: recording.duration_ms });
}
```

## Anti-patterns

- Awaiting each fetch sequentially when results are independent — the most common latency regression in example project Workers.
- Calling `waitUntil` with work that modifies the response — `waitUntil` runs after the response is sent; it cannot change what the client receives.
- Ignoring the 1 000 subrequest limit in list endpoints that loop over results and fetch R2 objects per row.
- Running CPU-intensive JS (large sort, JSON stringify of 5 MB objects) inside the request/response path — move to a Queue consumer or Durable Object for offline processing.
- Sending the same large desktop payload to mobile clients because `CF-Device-Type` was not checked — wastes mobile data and increases Time-to-Interactive.

## Gotchas

- **`waitUntil` CPU is not free**: a computationally expensive background task inside `waitUntil` can hit the CPU limit and cause the Worker to terminate mid-background-task. Keep background tasks lightweight; offload heavy work to Queues.
- **`Promise.all` failure semantics**: if any promise rejects, `Promise.all` rejects immediately and other in-flight requests are abandoned (but their network I/O may still be in flight and billed). Use `Promise.allSettled` when partial results are acceptable.
- **Service binding subrequests count toward the CALLING Worker's budget**: a fan-out through 3 service bindings uses 3 of the caller's 1 000 subrequests, not the callee's.
- **`fetch()` to Cloudflare-hosted resources (R2 presigned URLs, Workers routes on the same zone)** may be served from cache and count as 0 egress, but still count as 1 subrequest.
- **Mobile `CF-Device-Type` is not set on Workers routes by default**: it is set by Cloudflare's caching layer for HTML responses but may not be present on API routes unless the zone has "Device Type" detection enabled. Combine with UA header fallback.

## Verification

```bash
# Check CPU time and subrequest count via Logpush or Tail Workers
wrangler tail example project-api --format pretty | grep -E "cpuTime|subrequests"

# Manually test mobile vs desktop branching
curl -H "CF-Device-Type: mobile" https://example.com/api/recordings/abc-123 | wc -c
# Compare payload size vs:
curl https://example.com/api/recordings/abc-123 | wc -c

# Measure concurrent vs sequential latency
time curl -s https://example.com/api/recordings/abc-123 -o /dev/null
```

## Related

- `workers-waituntil-shared-post-response-budget.md` — `waitUntil` CPU budget details
- `workers-configurable-subrequest-budget.md` — raising the subrequest limit
- `workers-resource-limits.md` — full Workers limits reference
- `workers-fetch-api-patterns.md` — `fetch()` patterns in Workers
- `cache-device-type-segmentation-mobile-desktop.md` — CF-Device-Type detection
- `workers-analytics-engine.md` — AE writes inside `waitUntil`

## Sources

- Workers resource limits: https://developers.cloudflare.com/workers/platform/limits/
- `ExecutionContext.waitUntil`: https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- Subrequest limits: https://developers.cloudflare.com/workers/platform/limits/#subrequests
- Cloudflare device detection: https://developers.cloudflare.com/rules/transform/managed-transforms/reference/
