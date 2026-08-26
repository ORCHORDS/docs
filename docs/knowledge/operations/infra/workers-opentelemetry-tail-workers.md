# Cloudflare Workers Observability with OpenTelemetry and Tail Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Workers are ephemeral and stateless. A request that fails in production leaves no
persistent process to attach a debugger to, and `console.log` output is only visible in
`wrangler tail` — a real-time stream that requires an active terminal connection. For
production observability — distributed traces that span multiple Workers, latency breakdowns
by binding call, error rates aggregated over time — you need a structured telemetry
pipeline that survives the request lifecycle.

This article covers two complementary mechanisms: Tail Workers (the Workers-native event
stream) and the Workers OpenTelemetry SDK (structured spans exported to any OTLP backend).
It is distinct from `opentelemetry-collector-config.md`, which covers running the
OTel Collector as a sidecar on Kubernetes; this article is specific to the Cloudflare
Workers environment.

## Context

Cloudflare provides three observability primitives for Workers:

1. **`wrangler tail`**: Real-time log stream over WebSocket. Useful for development; not
   suitable for production (requires a live client, no retention).
2. **Tail Workers**: A special Worker that receives structured event payloads from any
   other Worker in your account via a `tail` consumer binding. The Tail Worker can write
   to Logpush, Analytics Engine, or any HTTP endpoint, giving you durable storage.
3. **Workers Traces / OTel export** (GA in 2024-2025): The `cloudflare:workers` OTel SDK
   lets you emit spans from your Worker code and export them to any OTLP-compatible backend
   (Honeycomb, Grafana Cloud Tempo, Jaeger, the Cloudflare Workers Observability dashboard).

All three complement each other: Tail Workers give you log-level event data (status codes,
errors, CPU time, logs); OTel spans give you structured trace data with custom attributes.

## Tail Workers

### Configuration

```toml
# wrangler.toml (main Worker)
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2026-06-01"

[[tail_consumers]]
service = "observability-tail"
```

```toml
# wrangler.toml (Tail Worker — separate Worker project)
name = "observability-tail"
main = "src/tail.ts"
compatibility_date = "2026-06-01"
```

The Tail Worker must be deployed to your account before the main Worker references it.

### Tail Worker handler

```typescript
// src/tail.ts
export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    for (const event of events) {
      const record = {
        timestamp: event.eventTimestamp,
        outcome:   event.outcome,           // "ok" | "exception" | "canceled" | "exceeded"
        cpuMs:     event.cpuTime,
        wallMs:    event.wallTime,
        scriptName: event.scriptName,
        logs:      event.logs.map(l => ({ level: l.level, message: l.message })),
        exceptions: event.exceptions.map(e => ({ name: e.name, message: e.message })),
        request:   null as unknown,
      };

      if (event.event && "request" in event.event) {
        record.request = {
          method: event.event.request.method,
          url:    event.event.request.url,
          cf:     event.event.request.cf,
        };
      }

      // Write to Logpush-compatible endpoint or Analytics Engine
      ctx.waitUntil(
        fetch(env.LOG_SINK_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json",
                     "Authorization": `Bearer ${env.LOG_SINK_TOKEN}` },
          body: JSON.stringify(record),
        })
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

### Writing to Analytics Engine from a Tail Worker

```typescript
// Emit a data point per request to Analytics Engine
env.ANALYTICS.writeDataPoint({
  blobs:   [event.outcome, record.request?.method ?? "unknown"],
  doubles: [event.cpuTime ?? 0, event.wallTime ?? 0],
  indexes: [event.scriptName ?? ""],
});
```

Bind the Analytics Engine dataset in the Tail Worker's `wrangler.toml`:

```toml
[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "worker_telemetry"
```

Query it via the GraphQL Analytics API:

```graphql
{
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      workersAnalyticsEngineAdaptiveGroups(
        limit: 100
        filter: { datetimeHour_geq: "2026-08-22T00:00:00Z" }
        orderBy: [count_DESC]
      ) {
        count
        avg { double1 }   # avg CPU time
        dimensions { blob1 blob2 }  # outcome, method
      }
    }
  }
}
```

## Workers OpenTelemetry SDK

The `cloudflare:workers` package (or `@microlabs/otel-cf-workers`) instruments your
Worker with the OTel API and exports spans to any OTLP endpoint.

### Install

```bash
npm install @microlabs/otel-cf-workers @opentelemetry/api
```

### Instrument a Worker

```typescript
// src/index.ts
import { instrument, ResolveConfigFn } from "@microlabs/otel-cf-workers";
import { trace, SpanStatusCode }        from "@opentelemetry/api";

export interface Env {
  DB:           D1Database;
  OTEL_ENDPOINT: string;   // e.g. https://api.honeycomb.io
  OTEL_TOKEN:   string;
}

const handler = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const tracer = trace.getTracer("api-worker", "1.0.0");

    return tracer.startActiveSpan("handle-request", async (span) => {
      span.setAttribute("http.method", request.method);
      span.setAttribute("http.url",    request.url);

      try {
        const { results } = await tracer.startActiveSpan("db.query", async (dbSpan) => {
          dbSpan.setAttribute("db.system", "d1");
          const res = await env.DB.prepare("SELECT * FROM items LIMIT 10").all();
          dbSpan.setAttribute("db.rows_returned", res.results.length);
          dbSpan.end();
          return res;
        });

        span.setStatus({ code: SpanStatusCode.OK });
        span.end();
        return Response.json({ items: results });
      } catch (err: unknown) {
        span.recordException(err as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        span.end();
        throw err;
      }
    });
  },
};

const config: ResolveConfigFn = (env: Env, _trigger) => ({
  exporter: {
    url:     env.OTEL_ENDPOINT + "/v1/traces",
    headers: { "x-honeycomb-team": env.OTEL_TOKEN },
  },
  service: { name: "api-worker" },
});

export default instrument(handler, config);
```

### Wrangler secrets for OTel credentials

```bash
wrangler secret put OTEL_ENDPOINT
# Enter: https://api.honeycomb.io

wrangler secret put OTEL_TOKEN
# Enter: your-honeycomb-api-key
```

## Logpush for structured log forwarding

Logpush ships Worker logs (from `console.log` and Tail Worker payloads) to S3, R2, or
HTTP endpoints without needing a Tail Worker at all — useful for simple log-only pipelines:

```bash
# Create a Logpush job via API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "workers-logs",
    "logpull_options": "fields=Event,EventTimestampMs,Outcome,Exceptions,Logs,ScriptName",
    "destination_conf": "r2://$R2_BUCKET/logs/{DATE}?account-id=$ACCOUNT_ID&access-key-id=$ACCESS_KEY&secret-access-key=$SECRET_KEY",
    "dataset": "workers_trace_events",
    "enabled": true
  }'
```

Logpush delivers in 5-minute batches by default. For near-real-time delivery, use a Tail
Worker instead (sub-second latency).

## Sampling strategy

Tracing every request at high throughput is expensive. Apply head-based sampling:

```typescript
const config: ResolveConfigFn = (env: Env) => ({
  exporter: {
    url:     env.OTEL_ENDPOINT + "/v1/traces",
    headers: { "x-honeycomb-team": env.OTEL_TOKEN },
  },
  service: { name: "api-worker" },
  sampling: {
    headSampler: {
      // Sample 10% of requests; always sample errors
      shouldSample: (_ctx, _traceId, _spanName, _spanKind, attrs) => {
        if (attrs["error"] === true) return { decision: 1 };
        return { decision: Math.random() < 0.1 ? 1 : 0 };
      },
    },
  },
});
```

## Anti-patterns

- Using `console.log` as the only observability mechanism — logs are ephemeral and
  unqueryable without a Tail Worker or Logpush job forwarding them.
- Exporting traces synchronously within the request handler — always wrap export calls in
  `ctx.waitUntil()` so they don't block the response.
- Sending traces to a Collector sidecar running in a VPC from a Worker — the Collector
  must be reachable over public HTTPS; Workers cannot reach private IPs.
- Exporting all traces without sampling at high QPS — at 10 M requests/day with 3 spans
  each, naive full export saturates most hobbyist OTLP plans within hours.
- Relying on Tail Worker logs for SLO alerting — Tail Worker delivery is best-effort;
  use Analytics Engine or an external metrics system for SLO counters.

## Gotchas

- Tail Workers run in a separate isolate from the invoking Worker. They cannot access the
  original Worker's bindings or memory — only the serialized event payload.
- The `tail` handler receives a batch of events, not one per invocation. Size the batch
  processing to handle up to 1,000 events per call during traffic spikes.
- `ctx.waitUntil()` in a Tail Worker extends the Tail Worker's own lifetime, not the
  original Worker's. The original request has already returned by the time the Tail Worker
  runs.
- Workers OTel export adds ~1–5 ms of serialization overhead per request. Measure impact
  before enabling on latency-sensitive paths.
- Logpush requires a verified destination (ownership proof) and a separate Logpush
  entitlement on Enterprise plans. Analytics Engine is available on the Workers Paid plan.

## Verification

```bash
# Tail in real time (dev only)
wrangler tail api-worker --format pretty

# Confirm Tail Worker is receiving events
wrangler tail observability-tail --format json | head -20

# Check Analytics Engine data via GraphQL
curl -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query":"{ viewer { accounts(filter:{accountTag:\"'$ACCOUNT_ID'\"}) { workersAnalyticsEngineAdaptiveGroups(limit:5 filter:{datetimeHour_geq:\"2026-08-22T00:00:00Z\"} orderBy:[count_DESC]) { count dimensions { blob1 } } } } }"}' | jq .

# Send a test request and verify trace appears in Honeycomb / Grafana
curl -v https://api.example.com/items
# Then check your OTLP backend for a trace with service.name=api-worker
```

## Related

- opentelemetry-collector-config.md
- cloudflare-workers-limits-resource-planning.md
- keda-cloudflare-queue-consumers.md
- monitoring-sla-slo-sli.md
- monitoring-stack-2026.md

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/workers/observability/logpush/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://github.com/evanderkoogh/otel-cf-workers
- https://opentelemetry.io/docs/what-is-opentelemetry/
- https://developers.cloudflare.com/logs/get-started/enable-destinations/
