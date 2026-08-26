# Workers Tail Handlers: Real-Time Log Pipeline and Edge Observability

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your Cloudflare Workers generate `console.log()` output and throw exceptions, but you can only see them via `wrangler tail` — a developer-only, ephemeral stream. In production you need structured logs delivered to a centralized observability platform (Datadog, Grafana Loki, Axiom, Honeycomb) without adding latency to the hot request path, without paying per-GB Logpush ingestion fees for raw HTTP traffic logs, and without pulling logs through an external collector that introduces an availability dependency. Workers Tail Handlers solve this: a second Worker receives a structured tail event for every request handled by the primary Worker, with full access to request metadata, response status, logs, and exceptions, running asynchronously after the response has been sent.

---

## Context

A **Tail Worker** (also called a Tail Handler) is a separate Cloudflare Worker that:
1. Receives a `TailEvent[]` payload after the primary Worker's response is sent to the client
2. Runs in its own isolate — failure does not affect the primary Worker's response
3. Has access to the same KV, D1, R2, and Queue bindings as any other Worker
4. Is triggered by Cloudflare's internal telemetry pipeline, not by a Queue or HTTP fan-out

The tail event payload includes:
- `event.request` — method, URL, headers (configurable redaction)
- `event.response` — status code
- `event.logs` — `console.*` calls with their arguments and timestamps
- `event.exceptions` — uncaught exceptions with message and stack
- `event.scriptName` — the primary Worker's script name
- `event.eventTimestamp` — Unix ms timestamp

Tail Workers process events with a maximum delay of ~1 second from primary Worker invocation.

---

## Section 1: Defining and Binding a Tail Worker

`wrangler.toml` for the primary Worker:

```toml
name             = "my-api"
main             = "src/worker.ts"
compatibility_date = "2026-08-01"

# Tail Worker binding — receives tail events from my-api
tail_consumers = [{ service = "my-api-tail" }]
```

`wrangler.toml` for the Tail Worker (separate project):

```toml
name             = "my-api-tail"
main             = "src/tail-worker.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "LOG_BUFFER"
id      = "..."

[[queues.producers]]
binding  = "LOG_QUEUE"
queue    = "log-drain"
```

The Tail Worker must be deployed independently before the primary Worker's `tail_consumers` binding takes effect. Deploy the tail Worker first, then deploy the primary.

---

## Section 2: Structured Log Processing in the Tail Handler

```typescript
// src/tail-worker.ts
interface Env {
  LOG_QUEUE:  Queue<StructuredLogEvent>;
  ENVIRONMENT: string;
}

interface StructuredLogEvent {
  ts:          number;
  script:      string;
  environment: string;
  traceId:     string | null;
  method:      string;
  url:         string;
  status:      number;
  durationMs:  number;
  logs:        Array<{ level: string; message: string; ts: number }>;
  exceptions:  Array<{ message: string; stack: string }>;
  hasError:    boolean;
}

export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    const structured = events.map(event => toStructuredEvent(event, env.ENVIRONMENT));

    // High-priority: flush exceptions immediately via Queue for alerting
    const errorEvents = structured.filter(e => e.exceptions.length > 0 || e.status >= 500);
    if (errorEvents.length > 0) {
      ctx.waitUntil(
        Promise.all(errorEvents.map(e => env.LOG_QUEUE.send(e)))
      );
    }

    // Batch all events (including non-errors) to the log drain queue
    ctx.waitUntil(
      Promise.all(structured.map(e => env.LOG_QUEUE.send(e)))
    );
  },
};

function toStructuredEvent(event: TraceItem, environment: string): StructuredLogEvent {
  const req = event.event && 'request' in event.event ? event.event.request : null;
  const res = event.event && 'response' in event.event ? event.event.response : null;

  // Extract trace ID from request headers if present
  const traceId = req?.headers['x-trace-id'] ?? req?.headers['cf-ray'] ?? null;

  return {
    ts:          event.eventTimestamp,
    script:      event.scriptName ?? 'unknown',
    environment,
    traceId,
    method:      req?.method ?? 'unknown',
    url:         req?.url ?? 'unknown',
    status:      res?.status ?? 0,
    durationMs:  event.wallTimeMs ?? 0,
    logs:        (event.logs ?? []).map(l => ({
      level:   l.level,
      message: l.message.join(' '),
      ts:      l.timestamp,
    })),
    exceptions: (event.exceptions ?? []).map(e => ({
      message: e.message,
      stack:   e.stack ?? '',
    })),
    hasError: (event.exceptions?.length ?? 0) > 0 || (res?.status ?? 0) >= 500,
  };
}
```

---

## Section 3: Log Drain via Queue Consumer — Forwarding to Axiom/Loki

The Queue consumer batches tail events and ships them to an external log platform in bulk:

```typescript
// src/log-drain-consumer.ts
interface Env {
  AXIOM_API_TOKEN: string;
  AXIOM_DATASET:   string;
  ENVIRONMENT:     string;
}

export default {
  async queue(batch: MessageBatch<StructuredLogEvent>, env: Env): Promise<void> {
    const events = batch.messages.map(m => m.body);

    // Axiom ingest endpoint — NDJSON
    const ndjson = events.map(e => JSON.stringify(e)).join('\n');

    const resp = await fetch(`https://api.axiom.co/v1/datasets/${env.AXIOM_DATASET}/ingest`, {
      method:  'POST',
      headers: {
        Authorization:  `Bearer ${env.AXIOM_API_TOKEN}`,
        'Content-Type': 'application/x-ndjson',
      },
      body: ndjson,
    });

    if (resp.ok) {
      batch.ackAll();
    } else {
      const text = await resp.text();
      console.error(`Log drain ingest failed (${resp.status}): ${text}`);
      // Let messages retry by not calling ackAll()
      batch.retryAll();
    }
  },
};
```

For Grafana Loki, convert to Loki's push format:

```typescript
function toLokiPayload(events: StructuredLogEvent[], env: string): object {
  return {
    streams: [
      {
        stream: { environment: env, source: 'cloudflare-workers' },
        values: events.map(e => [
          String(e.ts * 1_000_000), // nanoseconds
          JSON.stringify(e),
        ]),
      },
    ],
  };
}
```

---

## Section 4: Sampling for High-Traffic Workers

At 100,000 RPS, every tail event is a ~1 KB payload. Shipping all events to an external platform can cost hundreds of dollars per day. Implement head-based sampling in the tail handler:

```typescript
// src/tail-worker.ts — add sampling logic
const SAMPLE_RATE = 0.01; // 1% of non-error traffic

export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    const toSend: StructuredLogEvent[] = [];

    for (const event of events) {
      const structured = toStructuredEvent(event, env.ENVIRONMENT);

      // Always send errors and slow requests (> 1 s)
      if (structured.hasError || structured.durationMs > 1000) {
        toSend.push(structured);
        continue;
      }

      // Sample a fraction of healthy requests
      if (Math.random() < SAMPLE_RATE) {
        toSend.push({ ...structured, sampled: true } as any);
      }
    }

    if (toSend.length > 0) {
      ctx.waitUntil(
        Promise.all(toSend.map(e => env.LOG_QUEUE.send(e)))
      );
    }
  },
};
```

For deterministic sampling (so a traced request is always sampled end-to-end), use the trace ID as the hash input:

```typescript
function shouldSample(traceId: string | null, rate: number): boolean {
  if (!traceId) return Math.random() < rate;
  // FNV-1a 32-bit hash, modulo 100
  let hash = 2166136261;
  for (let i = 0; i < traceId.length; i++) {
    hash ^= traceId.charCodeAt(i);
    hash = (hash * 16777619) >>> 0;
  }
  return (hash % 100) < (rate * 100);
}
```

---

## Section 5: Alert Routing — Exceptions to PagerDuty

Send exception events directly to an alerting endpoint without going through the log pipeline:

```typescript
// src/tail-worker.ts — add alert routing
async function alertOnException(
  event: StructuredLogEvent,
  pdToken: string,
  ctx: ExecutionContext
): Promise<void> {
  if (event.exceptions.length === 0) return;

  const payload = {
    routing_key:  pdToken,
    event_action: 'trigger',
    dedup_key:    `${event.script}:${event.exceptions[0].message}`,
    payload: {
      summary:  `[${event.script}] ${event.exceptions[0].message}`,
      severity: 'error',
      source:   event.url,
      custom_details: {
        trace_id:   event.traceId,
        stack:      event.exceptions[0].stack,
        request:    `${event.method} ${event.url}`,
        status:     event.status,
        ts:         new Date(event.ts).toISOString(),
      },
    },
  };

  ctx.waitUntil(
    fetch('https://events.pagerduty.com/v2/enqueue', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    }).then(r => {
      if (!r.ok) console.error(`PagerDuty alert failed: ${r.status}`);
    })
  );
}
```

The `dedup_key` is a fingerprint of the error, preventing alert storms: the same exception type from the same Worker is deduplicated into a single PagerDuty incident.

---

## Section 6: Redacting Sensitive Data Before Logging

The tail event includes request headers and log arguments. Redact secrets before they reach external platforms:

```typescript
const REDACTED_HEADERS = new Set([
  'authorization',
  'cookie',
  'x-api-key',
  'cf-access-token',
]);

const REDACT_PATTERN = /\b(?:password|secret|token|key|credential)["']?\s*[:=]\s*["']?[\w\-]+/gi;

function redactHeaders(headers: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(headers).map(([k, v]) => [
      k,
      REDACTED_HEADERS.has(k.toLowerCase()) ? '[REDACTED]' : v,
    ])
  );
}

function redactLogMessage(message: string): string {
  return message.replace(REDACT_PATTERN, match => match.replace(/["']?[\w\-]+$/, '[REDACTED]'));
}

// Apply in toStructuredEvent():
logs: (event.logs ?? []).map(l => ({
  level:   l.level,
  message: redactLogMessage(l.message.join(' ')),
  ts:      l.timestamp,
})),
```

---

## Anti-patterns

- **Calling slow external APIs synchronously in the tail handler**: The tail handler has a CPU time limit. Long-running HTTP calls should be dispatched via `ctx.waitUntil()` or enqueued to a Cloudflare Queue for the consumer to handle.
- **Logging sensitive data in the primary Worker**: `console.log(request.headers.get('authorization'))` will appear verbatim in the tail event payload. Redact at the source.
- **Using a tail handler as a billing data source**: Tail events may be sampled or dropped under extreme load. For billing-critical event accounting, use an atomic Durable Object write or D1 row instead.
- **Setting very low Queue TTL on the log drain queue**: Log events are time-sensitive but not critical-path. A TTL of 24 hours is appropriate; shorter TTLs risk losing logs during transient downstream outages.
- **Deploying the primary Worker before the Tail Worker**: If the tail Worker is not yet deployed when the primary Worker's `tail_consumers` binding activates, tail events are discarded silently.

---

## Gotchas

- **Tail Worker CPU limit**: Tail Workers share the same 10 ms CPU budget as standard Workers. Offload heavy processing (JSON transformation, HTTP calls) to `ctx.waitUntil()`.
- **Log ordering is not guaranteed**: Tail events from the same primary Worker request may arrive out of order if the Worker spawned multiple microtasks. Sort by `l.timestamp` before displaying.
- **No tail events for sub-request Workers**: Tail Workers only receive events for the Worker bound in `tail_consumers`. Subrequests made by that Worker to other Workers are not automatically traced.
- **Header visibility**: By default, all request and response headers are included in tail events. Configure `logpush` settings in the Dashboard or via API to redact specific header names before they reach the tail Worker.
- **Tail Workers count against your Worker invocation quota**: Each primary Worker invocation triggers one tail Worker invocation. On a Paid plan this is generally fine; audit invocation count if costs increase unexpectedly.

---

## Verification

```bash
# Deploy tail Worker first
cd my-api-tail && wrangler deploy

# Deploy primary Worker with tail_consumers binding
cd my-api && wrangler deploy

# Send a test request that will generate logs
curl "https://my-api.example.com/test" -H "X-Trace-Id: test-trace-001"

# Verify log appears in Axiom / Loki within 2 seconds
# In Axiom:
#   axiom stream --dataset=workers-logs --filter='script="my-api"' --tail

# Verify exception alerting by sending a request to a known-broken endpoint
curl "https://my-api.example.com/throw"
# PagerDuty should receive a trigger event within 3 seconds

# Validate sampling rate against expected throughput
# Query Axiom: COUNT(*) WHERE sampled=true / COUNT(*) ≈ SAMPLE_RATE for non-error traffic
```

---

## Related

- `observability-architecture.md` — distributed tracing and observability overview
- `distributed-tracing-architecture.md` — trace propagation patterns
- `analytics-engine-event-pipeline.md` — Analytics Engine for custom metrics
- `dead-letter-queue-architecture.md` — handling failed log drain messages
- `temporal-decoupling-cloudflare-queues.md` — Queue semantics for async pipelines

---

## Sources

- Cloudflare Tail Workers documentation: https://developers.cloudflare.com/workers/observability/logging/tail-workers/
- Cloudflare Workers TraceItem type: https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/
- Cloudflare Logpush: https://developers.cloudflare.com/logs/
- Axiom Cloudflare Workers integration: https://axiom.co/docs/send-data/cloudflare-workers
- Grafana Loki push API: https://grafana.com/docs/loki/latest/reference/loki-http-api/#push-log-entries-to-loki
- PagerDuty Events API v2: https://developer.pagerduty.com/api-reference/YXBpOjI3NDgyNjU-pager-duty-v2-events-api
