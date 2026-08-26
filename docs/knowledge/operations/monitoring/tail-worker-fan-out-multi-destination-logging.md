# Tail Worker Fan-Out Multi-Destination Logging

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A single Tail Worker must simultaneously deliver structured log events to
multiple sinks — an external SIEM (e.g. Splunk HEC, Datadog Logs), an
Analytics Engine dataset for real-time querying, and an R2 bucket for
long-term retention — without one slow or failing destination blocking the
others or dropping events from healthy sinks.

---

## Context

A Tail Worker receives a `TailEvent` array from the platform on every
sampled invocation of its upstream Worker. It runs in a separate Worker
context with its own CPU and subrequest budget (currently 50 subrequest
limit per invocation). Fan-out means firing `fetch()` or `writeDataPoint()`
calls to N destinations concurrently and treating each outcome independently
so that one destination's 500 or timeout cannot cascade.

Key constraints:
- Subrequest limit: 50 per Tail Worker invocation (counts across all
  `fetch()` calls including retries).
- CPU time: 50 ms (free) / 30 000 ms (paid) unbundled time.
- `ctx.waitUntil()` keeps the Worker alive for async fan-out after the event
  handler returns synchronously.
- Analytics Engine `writeDataPoint()` is synchronous in-process and does not
  consume subrequest budget.

---

## Architecture

```
Upstream Worker
      │
      │ tail stream
      ▼
 Tail Worker
      │
      ├─ writeDataPoint()  ──► Analytics Engine dataset  (in-process, free)
      ├─ fetch() ────────────► External SIEM (HEC / Datadog)
      └─ fetch() ────────────► R2 HTTP API (object PUT)
```

Fan-out via `Promise.allSettled` ensures partial success: if the SIEM is
unreachable the R2 write still completes.

---

## TypeScript Implementation

### wrangler.toml

```toml
name = "log-fan-out-tail"
main = "src/tail.ts"
compatibility_date = "2025-09-01"

[[tail_consumers]]
service = "your-upstream-worker"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "worker_events"
```

### src/tail.ts

```typescript
export interface Env {
  AE: AnalyticsEngineDataset;
  SIEM_URL: string;       // e.g. https://http-inputs-xxx.splunkcloud.com/services/collector
  SIEM_TOKEN: string;
  R2_BUCKET_URL: string;  // https://<account>.r2.cloudflarestorage.com/<bucket>
  R2_ACCESS_KEY_ID: string;
  R2_SECRET_ACCESS_KEY: string;
}

export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(fanOut(events, env));
  },
};

async function fanOut(events: TraceItem[], env: Env): Promise<void> {
  const batch = events.map(normalise);

  // Analytics Engine — synchronous, no subrequest consumed
  for (const e of batch) {
    env.AE.writeDataPoint({
      blobs: [e.scriptName, e.outcome, e.exceptionMessage ?? ""],
      doubles: [e.cpuMs, e.wallMs],
      indexes: [e.rayId],
    });
  }

  // External SIEM and R2 run concurrently
  const results = await Promise.allSettled([
    sendToSiem(batch, env),
    sendToR2(batch, env),
  ]);

  for (const r of results) {
    if (r.status === "rejected") {
      // Surface as a structured console.error — do not rethrow
      console.error(JSON.stringify({ sink: "fan-out", error: String(r.reason) }));
    }
  }
}

interface NormalisedEvent {
  rayId: string;
  scriptName: string;
  outcome: string;
  cpuMs: number;
  wallMs: number;
  exceptionMessage?: string;
  timestamp: number;
}

function normalise(e: TraceItem): NormalisedEvent {
  const ex = e.exceptions?.[0];
  return {
    rayId: e.rayId ?? "",
    scriptName: e.scriptName ?? "unknown",
    outcome: e.outcome,
    cpuMs: e.cpuTime ?? 0,
    wallMs: e.wallTime ?? 0,
    exceptionMessage: ex ? `${ex.name}: ${ex.message}` : undefined,
    timestamp: Date.now(),
  };
}

// ── SIEM destination ──────────────────────────────────────────────────────────

async function sendToSiem(
  events: NormalisedEvent[],
  env: Env,
): Promise<void> {
  // Splunk HEC batch — one JSON object per line
  const body = events
    .map((e) => JSON.stringify({ time: e.timestamp / 1000, event: e }))
    .join("\n");

  const res = await fetch(env.SIEM_URL, {
    method: "POST",
    headers: {
      "Authorization": `Splunk ${env.SIEM_TOKEN}`,
      "Content-Type": "application/json",
    },
    body,
  });

  if (!res.ok) {
    throw new Error(`SIEM responded ${res.status}: ${await res.text()}`);
  }
}

// ── R2 destination via S3-compatible API ──────────────────────────────────────

async function sendToR2(
  events: NormalisedEvent[],
  env: Env,
): Promise<void> {
  const key = `logs/${new Date().toISOString().slice(0, 10)}/${Date.now()}.ndjson`;
  const body = events.map((e) => JSON.stringify(e)).join("\n");

  // Use AWS Signature v4 via a helper or a pre-signed URL stored in a secret
  // For simplicity here: pre-signed URL injected as env var per deployment
  const url = `${env.R2_BUCKET_URL}/${key}`;
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/x-ndjson" },
    body,
  });

  if (!res.ok) {
    throw new Error(`R2 PUT responded ${res.status}`);
  }
}
```

---

## Anti-patterns

**Awaiting destinations serially.**
```typescript
// WRONG — one slow SIEM times out and blocks R2
await sendToSiem(batch, env);
await sendToR2(batch, env);
```
Use `Promise.allSettled` so failures are independent.

**Re-throwing inside fan-out.**
If `fanOut` throws, the platform may retry the Tail Worker and produce
duplicate events at working destinations. Catch per-sink errors and log them.

**Calling `fetch()` inside a `for` loop over every event.**
This exhausts the 50-subrequest limit fast. Always batch events into a single
request per destination per invocation.

**Blocking the `tail()` handler.**
Do not `await fanOut(...)` directly in the `tail()` handler. Return quickly
and use `ctx.waitUntil(fanOut(...))` so the platform registers the promise.

---

## Gotchas

- `Promise.allSettled` requires the `es2021` lib target in `tsconfig.json`.
- Analytics Engine `writeDataPoint` silently drops data if you exceed 25
  blobs + doubles per call; normalise accordingly.
- Each `fetch()` to an external origin counts as one subrequest. If a
  destination is slow, the 30 s paid CPU budget is generous but the subrequest
  timeout is 30 s per request — set an `AbortSignal.timeout(10_000)` to
  avoid tying up the budget.
- Tail Workers inherit the same IP egress as the upstream script's colo,
  which may require allowlisting in your SIEM's firewall.

---

## Verification

1. Deploy the Tail Worker and trigger a few upstream requests.
2. Check Analytics Engine via the SQL API:
   ```sql
   SELECT blob1 AS script, blob2 AS outcome, count() AS n
   FROM worker_events
   WHERE timestamp > NOW() - INTERVAL '5' MINUTE
   GROUP BY script, outcome
   ```
3. In Splunk/Datadog confirm events arrive with the correct `time` field.
4. In R2 confirm NDJSON files appear under the `logs/YYYY-MM-DD/` prefix.
5. Simulate a SIEM outage (wrong URL) and confirm R2 still receives data and
   the error surfaces in Workers Logs under the Tail Worker script.

---

## Related

- `tail-worker-structured-log-sampling-strategies.md`
- `tail-worker-otel-span-export.md`
- `logpush-s3-compatible-r2-destination.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `workers-subrequest-limit-headroom-monitoring.md`

---

## Sources

- Cloudflare Workers Tail Workers docs — https://developers.cloudflare.com/workers/observability/tail-workers/
- Analytics Engine writeDataPoint reference — https://developers.cloudflare.com/analytics/analytics-engine/
- Workers subrequest limits — https://developers.cloudflare.com/workers/platform/limits/
