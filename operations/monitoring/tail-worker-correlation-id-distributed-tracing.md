# Tail Worker Correlation ID Distributed Tracing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A single user action fans out through three Workers, a D1 query, and two external API calls. When the D1 query is slow or the external call fails, logs from each hop appear in isolation — different Logpush jobs, different tail streams. You cannot reconstruct "what happened for request X" without manually correlating timestamps and guessing which subrequests belonged together. You need end-to-end correlation without an external tracing collector in the hot path.

## Context

Cloudflare Workers run across thousands of edge nodes. There is no shared in-process memory between Workers invocations and no sidecar agent that can inject trace headers automatically. The tail Worker receives a `TailEvent` per invocation after it completes, giving you structured access to every log, exception, subrequest, and the original request headers. That makes the tail Worker the natural place to harvest correlation IDs, resolve parent–child span relationships, and forward a single correlated payload to Analytics Engine or an external collector.

The pattern: **generate a trace ID at the entry-point Worker, propagate it via the `traceparent` / `X-Correlation-Id` headers on every downstream fetch call, emit it as a structured log field at each hop, then have a single tail Worker read those fields and assemble a trace record per invocation.**

---

## 1. Generating and Propagating a Correlation ID

Generate a W3C `traceparent`-compatible trace ID at the outermost Worker (the one receiving the user's request). Attach it to every downstream `fetch` call and to every log statement.

```typescript
// entry-worker/src/index.ts

export interface Env {
  INTERNAL_API: Fetcher; // service binding to a downstream Worker
}

function generateTraceId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function generateSpanId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function buildTraceparent(traceId: string, spanId: string): string {
  return `00-${traceId}-${spanId}-01`;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Honour an incoming traceparent from a trusted upstream; otherwise mint a new one.
    const inbound = request.headers.get("traceparent");
    const traceId = inbound ? inbound.split("-")[1] : generateTraceId();
    const spanId = generateSpanId();
    const traceparent = buildTraceparent(traceId, spanId);

    console.log(JSON.stringify({
      level: "info",
      event: "request.received",
      traceId,
      spanId,
      method: request.method,
      url: request.url,
    }));

    // Propagate to internal service binding
    const downstreamResponse = await env.INTERNAL_API.fetch(
      new Request("https://internal/process", {
        headers: {
          "traceparent": traceparent,
          "X-Correlation-Id": traceId,
        },
      }),
    );

    console.log(JSON.stringify({
      level: "info",
      event: "downstream.complete",
      traceId,
      spanId,
      downstreamStatus: downstreamResponse.status,
    }));

    return new Response("ok", { status: 200 });
  },
};
```

---

## 2. Extracting the Correlation ID in Downstream Workers

Each downstream Worker reads the `traceparent` header, creates its own child span ID, and emits structured logs with both the shared `traceId` and its local `spanId`.

```typescript
// downstream-worker/src/index.ts

import type { D1Database } from "@cloudflare/workers-types";

export interface Env {
  DB: D1Database;
}

function parseTraceId(traceparent: string | null): string {
  if (!traceparent) return "unknown";
  const parts = traceparent.split("-");
  return parts.length >= 2 ? parts[1] : "unknown";
}

function newSpanId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(8)),
    (b) => b.toString(16).padStart(2, "0")).join("");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const traceId = parseTraceId(request.headers.get("traceparent"));
    const spanId = newSpanId();
    const parentSpanId = request.headers.get("traceparent")?.split("-")[2] ?? "none";
    const t0 = Date.now();

    const { results } = await env.DB.prepare(
      "SELECT id, payload FROM jobs WHERE status = 'pending' LIMIT 10",
    ).all();

    const queryDurationMs = Date.now() - t0;

    console.log(JSON.stringify({
      level: "info",
      event: "d1.query.complete",
      traceId,
      spanId,
      parentSpanId,
      queryDurationMs,
      rowCount: results.length,
    }));

    return Response.json({ processed: results.length });
  },
};
```

---

## 3. Tail Worker — Harvesting and Correlating Spans

The tail Worker receives every invocation's `TailEvent`. It reads the structured log fields, reconstructs a lightweight span record, and writes it to Analytics Engine as a single correlated row.

```typescript
// tail-worker/src/index.ts

import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";

export interface Env {
  TRACE_DATASET: AnalyticsEngineDataset;
}

interface SpanLog {
  level: string;
  event: string;
  traceId?: string;
  spanId?: string;
  parentSpanId?: string;
  queryDurationMs?: number;
  downstreamStatus?: number;
  rowCount?: number;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const workerName = event.scriptName ?? "unknown";
      const wallTime = event.eventTimestamp;

      // Collect all structured logs from this invocation
      for (const log of event.logs) {
        let parsed: SpanLog;
        try {
          parsed = JSON.parse(typeof log.message[0] === "string"
            ? log.message[0]
            : JSON.stringify(log.message[0]));
        } catch {
          continue; // skip unstructured logs
        }

        if (!parsed.traceId || !parsed.spanId) continue;

        env.TRACE_DATASET.writeDataPoint({
          blobs: [
            parsed.traceId,          // blob1: trace ID
            parsed.spanId,            // blob2: span ID
            parsed.parentSpanId ?? "root", // blob3: parent span ID
            parsed.event,             // blob4: event name
            workerName,               // blob5: worker name
          ],
          doubles: [
            parsed.queryDurationMs ?? 0,    // double1: query duration
            parsed.downstreamStatus ?? 0,   // double2: HTTP status of subrequest
            parsed.rowCount ?? 0,           // double3: rows touched
            event.outcome === "ok" ? 1 : 0, // double4: success flag
          ],
          indexes: [parsed.traceId],   // index: enables per-trace filtering
        });
      }

      // Also capture exception spans
      for (const ex of event.exceptions) {
        env.TRACE_DATASET.writeDataPoint({
          blobs: ["unknown", "exception", "none", ex.name, workerName],
          doubles: [0, 500, 0, 0],
          indexes: [workerName],
        });
      }
    }
  },
};
```

---

## 4. Querying Correlated Traces in Analytics Engine

Reconstruct a full trace by joining on `blob1` (traceId) in the Analytics Engine SQL API.

```sql
-- Fetch all spans for a single trace in chronological order
SELECT
  blob2   AS span_id,
  blob3   AS parent_span_id,
  blob4   AS event,
  blob5   AS worker,
  double1 AS query_duration_ms,
  double2 AS downstream_status,
  double4 AS success,
  _sample_interval,
  toDateTime(timestamp) AS ts
FROM TRACE_DATASET
WHERE blob1 = 'a3f2c1e09b4d6f8a2c3e1b0f4d6a8c2e'  -- traceId
  AND timestamp > NOW() - INTERVAL '1' HOUR
ORDER BY ts ASC;
```

```typescript
// Query via Workers — expose a trace-by-id endpoint for internal tooling
export default {
  async fetch(request: Request, env: { CF_ACCOUNT_ID: string; AE_TOKEN: string }): Promise<Response> {
    const traceId = new URL(request.url).searchParams.get("traceId");
    if (!traceId || !/^[0-9a-f]{32}$/.test(traceId)) {
      return new Response("invalid traceId", { status: 400 });
    }

    const sql = `
      SELECT blob2 AS span, blob3 AS parent, blob4 AS event,
             blob5 AS worker, double1 AS dur_ms, double4 AS ok,
             toDateTime(timestamp) AS ts
      FROM TRACE_DATASET
      WHERE blob1 = '${traceId}'
        AND timestamp > NOW() - INTERVAL '1' HOUR
      ORDER BY ts ASC
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.AE_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: sql,
      },
    );

    return new Response(await res.text(), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 5. Alerting on Orphan Spans

Spans with a `parentSpanId` that never appears in the dataset indicate dropped hops — a Worker that crashed before emitting structured logs or bypassed the propagation pattern.

```sql
-- Orphan span count in the last hour (approximate — use as a canary)
SELECT
  blob5   AS worker,
  COUNT() AS orphan_spans
FROM TRACE_DATASET
WHERE blob3 != 'root'
  AND blob3 NOT IN (
    SELECT blob2
    FROM TRACE_DATASET
    WHERE timestamp > NOW() - INTERVAL '1' HOUR
  )
  AND timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY blob5
ORDER BY orphan_spans DESC;
```

Schedule a Worker cron trigger to run this hourly and POST to a Slack webhook if `orphan_spans` exceeds a threshold.

---

## Anti-patterns

- **Logging the trace ID as a bare string** — makes it impossible to parse with a consistent field name; always emit structured JSON with named keys.
- **Generating a new trace ID in the tail Worker** — the tail Worker must read the trace ID *from* the event's logs, not invent its own; otherwise every invocation looks unrelated.
- **Using `Request.cf.requestId` as the trace ID** — that ID is scoped to the outermost request and does not propagate automatically to service-binding calls or outbound fetches; you must propagate it manually.
- **Mixing W3C `traceparent` and a custom `X-Request-Id` without normalising** — pick one canonical field to index in Analytics Engine; two different fields double your cardinality with no benefit.

## Gotchas

- Tail Workers receive events asynchronously and may arrive **out-of-order** relative to wall time; sort by the `timestamp` field in Analytics Engine, not by the order events arrive.
- `console.log` in a Worker stringifies objects with `JSON.stringify` only if you explicitly call it; passing an object literal logs `[object Object]` in some runtimes. Always stringify before logging.
- The tail Worker's `TailEvent.logs` array only contains calls to `console.*`; spans emitted via `ctx.waitUntil` in the original Worker may arrive in a separate tail event if the runtime batches them.
- Analytics Engine `writeDataPoint` is fire-and-forget inside the tail Worker; wrap it in a try/catch to prevent a dataset-write failure from silently dropping all remaining events in the loop.

## Verification

```bash
# 1. Deploy entry and downstream workers with wrangler
wrangler deploy --config entry-worker/wrangler.toml
wrangler deploy --config downstream-worker/wrangler.toml
wrangler deploy --config tail-worker/wrangler.toml

# 2. Send a test request and capture the traceId from logs
curl -s https://entry.example.workers.dev/ | jq .

# 3. Within ~30 s, query Analytics Engine for that traceId
curl -s "https://trace-query.example.workers.dev/?traceId=<TRACE_ID>" | jq .

# 4. Confirm all expected worker names appear as blob5 values
# 5. Confirm no orphan spans in the result set
```

## Related

- `tail-worker-otel-span-export.md`
- `distributed-tracing-workers-d1-durable-objects-otel.md`
- `log-correlation-trace-context-propagation.md`
- `w3c-trace-context-propagation.md`
- `analytics-engine-sql-api-programmatic-querying.md`

## Sources

- Cloudflare Tail Workers documentation — developers.cloudflare.com/workers/observability/tail-workers
- W3C Trace Context Level 2 — w3.org/TR/trace-context
- Cloudflare Analytics Engine SQL API — developers.cloudflare.com/analytics/analytics-engine/sql-api
- Cloudflare Service Bindings — developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings
