# Workers Trace Events and Debug Tooling

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A production Worker is making unexpected subrequests, cache lookups are missing, or a KV read is mysteriously slow. `console.log` survives to Tail Workers but you need structured, machine-readable timing data — spans with start/end timestamps, subrequest URLs, cache hit/miss outcomes, and exception stack traces — without touching the Worker's own hot path or adding instrumentation code.

## Context

Cloudflare Workers supports three distinct observability primitives:

| Primitive | What you get | CPU overhead |
|---|---|---|
| `console.log` / Tail Workers | Text log lines after execution | Negligible |
| Logpush | Forwarded log events to R2 / Datadog / etc. | Negligible |
| **Trace Workers** | Structured `TraceItem[]` tree for every execution | Negligible (out-of-band) |

Trace Workers (also called "Trace event consumers") were introduced as a first-class binding type. A Trace Worker is a separate Worker whose entire job is to receive a batch of `TraceItem` objects from Cloudflare's internal tracing pipeline after the traced Worker completes. It runs out-of-band — the traced request's latency is not affected.

Each `TraceItem` carries:
- `event` — the trigger (fetch, scheduled, queue, etc.)
- `eventTimestampMs` — epoch ms when the event started
- `outcome` — `"ok"`, `"exception"`, `"exceeded-cpu"`, `"killed"`, etc.
- `logs[]` — array of `{ timestamp, level, message }` from `console.*` calls
- `exceptions[]` — array of `{ timestamp, name, message }` uncaught throws
- `scriptName` and `scriptVersion` for correlation
- `diagnosticsChannelEvents[]` — low-level diagnostics

## Wrangler Configuration

### Traced Worker (`wrangler.toml`)

```toml
name = "my-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

# No special config needed on the traced side;
# the trace binding is declared on the CONSUMER side.
```

### Trace Consumer Worker (`wrangler.toml`)

```toml
name = "my-trace-consumer"
main = "src/trace.ts"
compatibility_date = "2025-09-01"

[[tail_consumers]]
service = "my-api"
```

> **Note**: The binding key in `wrangler.toml` is `tail_consumers` for historical reasons — the Trace Worker API is delivered through the same binding infrastructure as Tail Workers but exposes a richer typed interface via `ExportedHandlerTailHandler`.

## Implementing a Trace Consumer

```typescript
// src/trace.ts
export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    for (const event of events) {
      const base = {
        script: event.scriptName,
        version: event.scriptVersion?.id,
        outcome: event.outcome,
        startMs: event.eventTimestampMs,
      };

      // Structured fetch trigger details
      if (event.event && 'request' in event.event) {
        const req = event.event.request;
        const resp = event.event.response;
        const record = {
          ...base,
          type: 'fetch',
          method: req.method,
          url: req.url,
          cfRay: req.headers['cf-ray'],
          statusCode: resp?.status,
          durationMs: event.eventTimestampMs
            ? Date.now() - event.eventTimestampMs
            : undefined,
        };
        await forwardToOtel(record, env);
      }

      // Capture exceptions with stack context
      for (const exc of event.exceptions ?? []) {
        await forwardToOtel(
          {
            ...base,
            type: 'exception',
            name: exc.name,
            message: exc.message,
            timestamp: exc.timestamp,
          },
          env,
        );
      }

      // Re-surface console.error lines as alerts
      for (const log of event.logs ?? []) {
        if (log.level === 'error') {
          await forwardToOtel({ ...base, type: 'log', level: log.level, message: log.message[0] }, env);
        }
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function forwardToOtel(record: Record<string, unknown>, env: Env): Promise<void> {
  // env.OTEL_ENDPOINT is an OTLP HTTP endpoint secret
  await fetch(env.OTEL_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.OTEL_TOKEN}` },
    body: JSON.stringify(record),
  });
}
```

## Capturing Subrequest Spans with `diagnosticsChannelEvents`

The `diagnosticsChannelEvents` array carries low-level events published via the Node.js `diagnostics_channel` module inside the Workers runtime. Use it to capture subrequest timing:

```typescript
// Filter diagnosticsChannelEvents for fetch spans
function extractSubrequestSpans(event: TraceItem): SubrequestSpan[] {
  const spans: SubrequestSpan[] = [];
  for (const dc of event.diagnosticsChannelEvents ?? []) {
    if (dc.channel === 'cloudflare:workers:fetch-request') {
      spans.push({
        url: String(dc.message.url),
        method: String(dc.message.method),
        startMs: dc.timestamp,
      });
    }
    if (dc.channel === 'cloudflare:workers:fetch-response') {
      const last = spans.findLast((s) => s.url === String(dc.message.url));
      if (last) {
        last.endMs = dc.timestamp;
        last.status = Number(dc.message.status);
        last.cacheStatus = String(dc.message.cfCacheStatus ?? 'UNKNOWN');
      }
    }
  }
  return spans;
}

interface SubrequestSpan {
  url: string;
  method: string;
  startMs: number;
  endMs?: number;
  status?: number;
  cacheStatus?: string;
}
```

## Forwarding Traces to Grafana Tempo (OTLP)

```typescript
// Convert Cloudflare trace to OpenTelemetry ResourceSpans
function toOtlpSpan(item: TraceItem, sub: SubrequestSpan) {
  return {
    traceId: item.event && 'request' in item.event
      ? item.event.request.headers['cf-ray'] ?? crypto.randomUUID()
      : crypto.randomUUID(),
    spanId: crypto.randomUUID().slice(0, 16),
    name: `fetch ${sub.url}`,
    startTimeUnixNano: String(sub.startMs * 1_000_000),
    endTimeUnixNano: String((sub.endMs ?? sub.startMs) * 1_000_000),
    status: { code: sub.status && sub.status >= 400 ? 2 : 1 },
    attributes: [
      { key: 'http.url', value: { stringValue: sub.url } },
      { key: 'http.method', value: { stringValue: sub.method } },
      { key: 'http.status_code', value: { intValue: sub.status } },
      { key: 'cf.cache_status', value: { stringValue: sub.cacheStatus } },
    ],
  };
}
```

## Local Development with `wrangler tail`

During local dev the full TraceItem API is not emitted; use `wrangler tail`:

```bash
# Stream structured JSON logs from a deployed Worker
wrangler tail my-api --format=json | jq '.exceptions[].message'

# Filter to only exceptions
wrangler tail my-api --status=error

# Filter by sampling (10% of requests)
wrangler tail my-api --sampling-rate=0.1
```

For local unit tests of the consumer itself:

```typescript
// test/trace.test.ts
import { describe, it, expect, vi } from 'vitest';
import worker from '../src/trace';

const mockEvent: TraceItem = {
  scriptName: 'my-api',
  outcome: 'ok',
  eventTimestampMs: Date.now(),
  logs: [],
  exceptions: [],
  diagnosticsChannelEvents: [],
  event: {
    request: { url: 'https://example.com/api', method: 'GET', headers: {} },
    response: { status: 200 },
  },
};

it('processes a trace event without throwing', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('ok'));
  await worker.tail([mockEvent], { OTEL_ENDPOINT: 'https://otel.example.com', OTEL_TOKEN: 'tok' } as any, {} as any);
  expect(fetchSpy).toHaveBeenCalledOnce();
});
```

## Anti-patterns

- **Performing heavy work synchronously inside `tail()`** — the tail handler runs post-response but still consumes CPU quota; use `ctx.waitUntil()` for slow I/O.
- **Forwarding every log line to a paid SaaS** — filter to errors/exceptions only or sample at the Cloudflare layer (`sampling-rate`) before shipping.
- **Assuming `eventTimestampMs` is wall-clock end time** — it is the *start* of the event. Compute duration from `diagnosticsChannelEvents` or from the last log timestamp.
- **Confusing Tail Workers with Trace Workers** — both use the `tail_consumers` binding but Trace Workers get the richer typed `TraceItem[]` array; legacy Tail Workers using the older `TailEvent` type see a flatter structure.

## Gotchas

- Trace consumers are not available on the free plan; they require a Workers Paid subscription.
- A Worker can have at most **one** tail consumer registered at a time.
- `diagnosticsChannelEvents` is only populated if the traced Worker opted into the `nodejs_compat` compatibility flag or the runtime emits them automatically. As of 2026, fetch subrequest channels are emitted by default.
- Trace consumers do **not** receive events when the Worker is called from a service binding; only top-level invocations (HTTP, cron, queue) produce trace events.
- The `outcome` field value `"exceeded-cpu"` means the 10 ms CPU burst was hit on the Standard usage model; `"killed"` means the 30-second wall-clock limit was reached.
- Sampling at the dashboard level applies before the trace consumer receives data, so your consumer cannot reconstruct 100% of traffic if sampling is active.

## Verification

```bash
# 1. Deploy traced worker and consumer
wrangler deploy --config wrangler-api.toml
wrangler deploy --config wrangler-trace.toml

# 2. Send a test request
curl -i https://my-api.example.workers.dev/test

# 3. Confirm the trace consumer received the event
wrangler tail my-trace-consumer --format=pretty

# 4. Check Grafana Tempo for the OTLP span within ~5 seconds
```

## Related

- `workers-tail-workers.md` — legacy tail workers using the `TailEvent` interface
- `workers-logpush.md` — push logs to R2, Datadog, New Relic, Splunk
- `workers-observability-logs-metrics-2026.md` — full observability stack overview
- `workers-analytics-engine.md` — writing custom metrics from inside the traced Worker

## Sources

- https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/
- https://developers.cloudflare.com/workers/observability/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
