# Workers Tail Real-Time Log Streaming Pipeline

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

`wrangler tail` gives individual developers a live view of a single Worker's
logs during active development — but it is tied to a CLI session, targets one
Worker at a time, and drops events under high load. Production teams need a
durable, multi-Worker, low-latency log pipeline: every request event, exception,
and console output from every edge Worker flows into a central sink (Loki,
Datadog, Axiom, or a self-hosted endpoint) in near-real-time, without polling
or sampling losses.

Workers Tail Workers — a first-class Cloudflare product — solve this. A Tail
Worker is an ordinary Cloudflare Worker that receives batched `TraceItem` events
from one or more producer Workers and can forward, filter, enrich, and route
them to any HTTP sink.

## Context

The Tail Worker model is an event-driven push pipeline:

```
[Producer Worker A] ──┐
[Producer Worker B] ──┼──► [Tail Worker] ──► [Sink: Loki / Datadog / custom]
[Producer Worker C] ──┘
```

Each event batch arrives as an array of `TraceItem` objects containing:

- `scriptName` — the originating Worker
- `outcome` — `"ok"`, `"exception"`, `"canceled"`, `"exceededCpu"`, etc.
- `startTime` / `endTime` — wall-clock timestamps
- `logs` — `console.log` / `.error` / `.warn` output with timestamps
- `exceptions` — thrown errors with message and stack
- `request` / `response` — HTTP metadata (method, URL, status code,
  content-length)
- `event.request.headers` — request headers (subject to PII filtering)
- `cpuTime` — CPU duration in milliseconds
- `wallTime` — total wall time in milliseconds

The Tail Worker receives these batches asynchronously after the producing
Worker's request completes, so it does not add latency to the request path.

## Tail Worker Architecture

### Wrangler Configuration

```toml
# tail-worker/wrangler.toml
name = "log-streaming-tail"
main = "src/index.ts"
compatibility_date = "2024-11-01"

[[tail_consumers]]
service = "api-gateway"

[[tail_consumers]]
service = "auth-worker"

[[tail_consumers]]
service = "image-transform"

[vars]
LOG_SINK = "loki"   # or "datadog", "axiom", "custom"
ENVIRONMENT = "production"
```

Each `[[tail_consumers]]` entry attaches this Tail Worker to a producer. A
single Tail Worker can tail up to 10 producers; use multiple Tail Workers for
larger deployments.

### Core Tail Worker

```typescript
// src/index.ts
import { TraceItem } from "@cloudflare/workers-types";
import { toLokiStreams } from "./sinks/loki";
import { toDatadogLogs } from "./sinks/datadog";
import { filterPII } from "./pii";
import { shouldSample } from "./sampling";

interface Env {
  LOG_SINK: string;
  ENVIRONMENT: string;
  LOKI_ENDPOINT: string;
  LOKI_BASIC_AUTH: string;
  DATADOG_API_KEY: string;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    const filtered = events
      .filter((e) => shouldSample(e))
      .map((e) => filterPII(e));

    if (filtered.length === 0) return;

    switch (env.LOG_SINK) {
      case "loki":
        await sendToLoki(filtered, env);
        break;
      case "datadog":
        await sendToDatadog(filtered, env);
        break;
      default:
        console.error(`Unknown LOG_SINK: ${env.LOG_SINK}`);
    }
  },
};
```

## Event Processing

### Normalizing TraceItems

Convert heterogeneous `TraceItem` fields into a flat, structured log record:

```typescript
// src/normalize.ts
export interface LogRecord {
  timestamp: string;
  level: "info" | "warn" | "error" | "critical";
  message: string;
  service: string;
  environment: string;
  outcome: string;
  httpMethod?: string;
  httpUrl?: string;
  httpStatus?: number;
  cpuMs?: number;
  wallMs?: number;
  traceId?: string;
  spanId?: string;
}

export function normalizeTraceItem(
  item: TraceItem,
  environment: string
): LogRecord[] {
  const records: LogRecord[] = [];

  // HTTP outcome record
  records.push({
    timestamp: new Date(item.startTime).toISOString(),
    level: item.outcome === "exception" ? "error"
         : item.outcome === "ok" ? "info"
         : "warn",
    message: item.outcome === "exception"
      ? (item.exceptions?.[0]?.message ?? "unhandled exception")
      : `${item.event?.request?.method ?? "?"} ${item.event?.request?.url ?? "?"}`,
    service: item.scriptName ?? "unknown",
    environment,
    outcome: item.outcome,
    httpMethod: item.event?.request?.method,
    httpUrl: sanitizeUrl(item.event?.request?.url),
    httpStatus: item.response?.status,
    cpuMs: item.cpuTime,
    wallMs: (item.endTime ?? item.startTime) - item.startTime,
    traceId: item.event?.request?.headers?.["traceparent"]?.split("-")[1],
  });

  // Console log records
  for (const log of item.logs ?? []) {
    records.push({
      timestamp: new Date(log.timestamp).toISOString(),
      level: log.level === "error" ? "error"
           : log.level === "warn" ? "warn"
           : "info",
      message: log.message.map(String).join(" "),
      service: item.scriptName ?? "unknown",
      environment,
      outcome: item.outcome,
    });
  }

  return records;
}

function sanitizeUrl(url?: string): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    // Strip query params that may contain tokens
    u.search = "";
    return u.toString();
  } catch {
    return url;
  }
}
```

### Sampling Logic

High-traffic Workers can generate millions of events per minute. Sample
intelligently to reduce downstream cost:

```typescript
// src/sampling.ts
export function shouldSample(event: TraceItem): boolean {
  // Always forward errors and exceptions
  if (event.outcome === "exception" || event.outcome === "exceededCpu") {
    return true;
  }
  // Sample successful requests at 10%
  if (event.outcome === "ok") {
    return Math.random() < 0.10;
  }
  // Forward all other outcomes (canceled, exceededMemory, etc.)
  return true;
}
```

## Loki Sink

```typescript
// src/sinks/loki.ts
export async function sendToLoki(
  records: LogRecord[],
  env: { LOKI_ENDPOINT: string; LOKI_BASIC_AUTH: string }
): Promise<void> {
  const streams = groupByService(records).map(([service, recs]) => ({
    stream: { service, job: "cloudflare-workers" },
    values: recs.map((r) => [
      String(BigInt(new Date(r.timestamp).getTime()) * 1_000_000n),
      JSON.stringify(r),
    ]),
  }));

  const response = await fetch(`${env.LOKI_ENDPOINT}/loki/api/v1/push`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Basic ${env.LOKI_BASIC_AUTH}`,
    },
    body: JSON.stringify({ streams }),
  });

  if (!response.ok) {
    console.error(
      `Loki push failed: ${response.status} ${await response.text()}`
    );
  }
}

function groupByService(
  records: LogRecord[]
): Array<[string, LogRecord[]]> {
  const map = new Map<string, LogRecord[]>();
  for (const r of records) {
    const existing = map.get(r.service) ?? [];
    existing.push(r);
    map.set(r.service, existing);
  }
  return Array.from(map.entries());
}
```

## Datadog Sink

```typescript
// src/sinks/datadog.ts
export async function sendToDatadog(
  records: LogRecord[],
  env: { DATADOG_API_KEY: string; ENVIRONMENT: string }
): Promise<void> {
  const payload = records.map((r) => ({
    ddsource: "cloudflare-workers",
    ddtags: `env:${env.ENVIRONMENT},service:${r.service}`,
    hostname: "cloudflare-edge",
    message: r.message,
    service: r.service,
    status: r.level,
    timestamp: new Date(r.timestamp).getTime(),
    ...r,
  }));

  await fetch("https://http-intake.logs.datadoghq.com/api/v2/logs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "DD-API-KEY": env.DATADOG_API_KEY,
    },
    body: JSON.stringify(payload),
  });
}
```

## High-Throughput Considerations

At scale (> 1 million requests/minute across tailed Workers), the Tail Worker
itself may approach CPU limits. Mitigations:

1. **Shard by Worker name.** Deploy separate Tail Workers per producer group.
   Each Tail Worker handles a subset of services.
2. **Use `waitUntil` for async sink writes.** The `tail()` handler should
   return quickly; sink HTTP calls go through `ctx.waitUntil`.
3. **Batch Loki pushes.** Loki's batch size limit is 4 MB per push. Chunk
   records before sending if the batch exceeds 3 MB.
4. **Circuit break on sink failures.** If the sink returns 5xx three times in
   a row, skip subsequent batches for 60 seconds to avoid exhausting Tail
   Worker CPU budget on failed retries.

## Anti-patterns

**Logging full request and response bodies.** TraceItem does not expose
response bodies by default, and you should not add them — body logging at
edge scale generates enormous log volume and surfaces PII. Log metadata only.

**One Tail Worker per producer Worker.** You can attach multiple producers to
one Tail Worker. Creating N Tail Workers for N producers multiplies
management overhead unnecessarily.

**Using the Tail Worker as a real-time alerting system.** The Tail Worker has
no direct way to page PagerDuty reliably if it itself is in a failure loop.
Use the streaming data in Loki/Datadog/Axiom for alerting; keep the Tail
Worker focused on log forwarding.

**Not handling Tail Worker exceptions.** If the Tail Worker throws, Cloudflare
silently drops that event batch. Wrap the entire `tail()` body in a try/catch
that logs the error to `console.error` (which Cloudflare captures in its own
system logs).

## Gotchas

- **Tail Worker invocation limits.** Tail Workers count against your account's
  Worker invocation limits. At very high traffic, the 10 million free
  invocations/day can be consumed quickly. Enable sampling or use a Logpush
  job for extremely high-volume logs.
- **Event batching is not guaranteed.** Cloudflare batches events for
  efficiency, but a single-request low-traffic Worker may deliver batches of
  one. Do not assume batch size.
- **`startTime` is epoch milliseconds, not ISO.** Convert with
  `new Date(item.startTime).toISOString()` before forwarding.
- **Headers are not always present.** `item.event?.request?.headers` may be
  undefined for non-HTTP triggers (scheduled Workers, Queue consumers). Guard
  all header access.
- **Tail Workers do not receive their own trace.** A Tail Worker tailing
  itself creates a loop. Cloudflare prevents this, but be aware when building
  catch-all tail configurations.

## Verification

1. Deploy the Tail Worker with `LOG_SINK=loki` and send 10 test requests to a
   tailed producer Worker.
2. Query Loki: `{job="cloudflare-workers"} | json | service="api-gateway"`
   and confirm 10 records appear within 30 seconds.
3. Trigger an exception in the producer and confirm it arrives in Loki with
   `level=error` and the exception message.
4. Ramp to 1,000 requests/min and confirm no Tail Worker CPU exceeded events
   appear in the Cloudflare dashboard.
5. Verify PII fields (authorization headers, email parameters) are absent from
   the forwarded log records.

## Related

- `cloudflare-workers-tail-debugging.md`
- `workers-tail-worker-pii-minimization-and-otel-decision.md`
- `grafana-loki-integration.md`
- `loki-logql-queries.md`
- `workers-logpush-observability-pipeline.md`

## Sources

- Cloudflare Workers Tail Workers documentation (2024)
- Cloudflare Tail Workers pricing and limits
- Grafana Loki HTTP API documentation
- Datadog Log Intake API documentation
- "Observability at the Edge with Tail Workers" — Cloudflare Blog, 2024
