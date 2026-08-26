# Tracing Async Operations Across Cloudflare Queues

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A user submits a form, a Worker enqueues a message, a consumer Worker processes it minutes later — and when the processing fails, the error log references a message ID but has no connection to the originating HTTP request. You cannot answer "which user triggered this failure?" or "how long did the full queue-to-completion cycle take?" without reading traces, logs, and queue dead-letter dumps in parallel and stitching them together by hand.

## Context

Cloudflare Queues decouples a producer Worker (the one that calls `env.QUEUE.send()`) from one or more consumer Workers (the ones declared in `wrangler.toml` under `[[queues.consumers]]`). This async boundary breaks standard request-scoped tracing: each consumer invocation has its own `executionCtx`, its own trace ID, and no direct link to the producer's span.

The solution is **trace context propagation through the message body** (or message metadata). W3C Trace Context defines `traceparent` and `tracestate` headers for exactly this purpose. Queues messages are arbitrary blobs, so you embed the propagation values as top-level fields in the JSON payload. On the consumer side you extract them and create a child span that links back to the producer.

This pattern requires:
- OpenTelemetry SDK in both producer and consumer Workers.
- A structured JSON message format (not raw strings).
- A consistent `traceId` propagation strategy for multi-hop chains (Queue → Queue, Queue → external API, etc.).

## Propagating Trace Context Through Queue Messages

### Producer Worker

```javascript
// producer/src/index.js
import { trace, context, propagation } from '@opentelemetry/api';

export default {
  async fetch(request, env, ctx) {
    const tracer = trace.getTracer('producer-worker');

    return tracer.startActiveSpan('handle-submit', async (span) => {
      const body = await request.json();

      // Extract W3C trace context to embed in the message
      const carrier = {};
      propagation.inject(context.active(), carrier);
      // carrier now has: { traceparent: '00-<traceId>-<spanId>-01', tracestate: '' }

      const message = {
        _tracing: carrier,          // trace context for downstream
        _producedAt: Date.now(),    // for queue latency measurement
        data: body,
      };

      await env.PROCESSING_QUEUE.send(message, {
        contentType: 'json',
        // Optional: set a deduplication ID if your queue supports it
      });

      span.setAttribute('queue.name', 'PROCESSING_QUEUE');
      span.setAttribute('message.produced_at', message._producedAt);
      span.end();

      return new Response(JSON.stringify({ queued: true }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      });
    });
  },
};
```

### Consumer Worker

```javascript
// consumer/src/index.js
import { trace, context, propagation } from '@opentelemetry/api';

export default {
  async queue(batch, env, ctx) {
    const tracer = trace.getTracer('consumer-worker');

    for (const message of batch.messages) {
      const body = message.body; // already parsed JSON because contentType: 'json'

      // Restore the trace context from the message
      const remoteContext = propagation.extract(context.active(), body._tracing ?? {});

      // Start a child span linked to the producer's span
      await context.with(remoteContext, async () => {
        return tracer.startActiveSpan(
          'process-queue-message',
          { kind: trace.SpanKind.CONSUMER },
          async (span) => {
            span.setAttribute('messaging.system', 'cloudflare-queues');
            span.setAttribute('messaging.operation', 'process');
            span.setAttribute('message.id', message.id);
            span.setAttribute('message.attempts', message.attempts);

            if (body._producedAt) {
              const queueLatencyMs = Date.now() - body._producedAt;
              span.setAttribute('queue.latency_ms', queueLatencyMs);
            }

            try {
              await processMessage(body.data, env, span);
              message.ack();
              span.setStatus({ code: trace.SpanStatusCode.OK });
            } catch (err) {
              span.recordException(err);
              span.setStatus({ code: trace.SpanStatusCode.ERROR, message: err.message });

              // Retry logic: nack returns message to queue up to max_retries
              if (message.attempts < 3) {
                message.retry({ delaySeconds: message.attempts * 30 });
              } else {
                // Exhausted retries — ack to remove from queue, log to dead-letter store
                await writeDeadLetter(message, err, env);
                message.ack();
              }
            } finally {
              span.end();
            }
          }
        );
      });
    }
  },
};

async function processMessage(data, env, parentSpan) {
  const tracer = trace.getTracer('consumer-worker');
  return tracer.startActiveSpan('do-work', async (span) => {
    // business logic here
    span.end();
  });
}
```

## Measuring Queue Latency as a Custom Metric

Queue processing latency is not surfaced in the Cloudflare dashboard out of the box. Capture it as a custom metric using Analytics Engine alongside your trace spans.

```javascript
// Inside the consumer's queue handler, after computing queueLatencyMs:
async function recordQueueMetrics(env, queueName, latencyMs, success) {
  env.ANALYTICS.writeDataPoint({
    blobs: [
      queueName,
      success ? 'success' : 'failure',
    ],
    doubles: [
      latencyMs,
      1, // message count
    ],
    indexes: [queueName],
  });
}
```

Query in Analytics Engine:

```sql
-- P95 queue latency over the last 24 hours, by queue name
SELECT
  blob1                                                  AS queue_name,
  blob2                                                  AS outcome,
  quantileWeighted(0.50)(double1, double2)               AS p50_latency_ms,
  quantileWeighted(0.95)(double1, double2)               AS p95_latency_ms,
  SUM(double2)                                           AS total_messages
FROM queue_metrics
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY queue_name, outcome
ORDER BY p95_latency_ms DESC
```

## Handling Multi-Hop Chains: Queue → Queue

When a consumer re-enqueues a message to a second queue, the trace context must be re-propagated through each hop. Always embed the current active context at enqueue time — the active context in the consumer span already includes the producer's trace ID as the root, so all hops share the same `traceId` and form a single distributed trace.

```javascript
// Inside a consumer that re-enqueues to a second queue
async function requeue(data, env) {
  const tracer = trace.getTracer('consumer-worker');
  return tracer.startActiveSpan('requeue-to-secondary', async (span) => {
    const carrier = {};
    propagation.inject(context.active(), carrier);

    await env.SECONDARY_QUEUE.send({
      _tracing: carrier,
      _producedAt: Date.now(),
      data,
    }, { contentType: 'json' });

    span.setAttribute('queue.name', 'SECONDARY_QUEUE');
    span.end();
  });
}
```

In your trace viewer (Jaeger, Grafana Tempo, Honeycomb) the complete trace will show:
```
[HTTP Request → Producer]
  └── [Queue Message → Consumer 1]
        └── [Requeue → Consumer 2]
              └── [DB write]
```

## Dead-Letter Observability

Messages that exhaust retries are typically acked (to prevent infinite redelivery) and written to a secondary store for analysis. Include the full trace context in the dead-letter record so you can correlate it with traces.

```javascript
async function writeDeadLetter(message, error, env) {
  const record = {
    messageId: message.id,
    attempts: message.attempts,
    body: message.body,
    error: {
      name: error.name,
      message: error.message,
      stack: error.stack,
    },
    deadLetteredAt: new Date().toISOString(),
    // Preserve trace context for correlation
    tracing: message.body?._tracing ?? {},
  };

  // Write to R2 for archival and ad-hoc querying
  const key = `dead-letter/${new Date().toISOString().slice(0, 10)}/${message.id}.json`;
  await env.DLQ_BUCKET.put(key, JSON.stringify(record), {
    httpMetadata: { contentType: 'application/json' },
  });

  // Also write an Analytics Engine event so you can alert on DLQ rate
  env.ANALYTICS.writeDataPoint({
    blobs: ['dead-letter', error.name],
    doubles: [1, message.attempts],
    indexes: [message.id],
  });
}
```

Set an alert when `SUM(double1)` on the dead-letter dataset exceeds a threshold over a rolling window — this signals messages failing faster than manual review can handle.

## Anti-patterns

- **Using `message.id` alone as a correlation key** — `message.id` is unique per message but has no link to the originating HTTP request. Without trace propagation, you cannot reconstruct the user journey end-to-end.
- **Embedding the full span object in the message** — spans are not serializable. Only the W3C `traceparent`/`tracestate` strings need to travel with the message.
- **Not recording `_producedAt`** — without a producer timestamp, you cannot measure queue-to-consumer latency, which is often the first signal of a consumer backlog.
- **Acking on exception to avoid retry storms** — unconditional `message.ack()` in the catch block silently discards messages. Use retry with exponential delay and only ack after writing to dead-letter storage.
- **Single-span for the entire batch** — `batch.messages` can contain up to 100 messages. Starting one span per batch collapses all message-level context. Start a child span per message.

## Gotchas

- **Consumer Workers do not have access to the original HTTP `request` object** — the only context available is what you embedded in the message body. Design your message schema to include all correlation fields before you ship.
- **`batch.ackAll()` / `batch.retryAll()`** — convenience methods that operate on the whole batch. Using them prevents per-message outcome tracking in traces. Use per-message `ack()` and `retry()` for observability granularity.
- **Clock skew between producer and consumer** — producer and consumer Workers run in different isolates, potentially on different edge nodes. `_producedAt` timestamps are from the producer's `Date.now()`, which may not be synchronized to the millisecond with the consumer's clock. Use the difference only as an approximation of latency; do not use it for billing or SLA enforcement.
- **Retry `delaySeconds` maximum** — as of 2025, the maximum retry delay via `message.retry({ delaySeconds })` is 43,200 seconds (12 hours). Beyond that, set `delaySeconds` to 43200.

## Verification

1. Trigger a producer request with a known test payload and capture the `traceparent` from the span.
2. In your trace backend, search by trace ID — you should see both the producer HTTP span and the consumer queue-processing span linked under the same trace.
3. Introduce a deliberate error and confirm the dead-letter R2 object is written with the correct `tracing` field.
4. Query Analytics Engine for `p95_latency_ms` and compare to the observed span duration — they should agree within 10%.

## Related

- `distributed-tracing-workers-d1-durable-objects-otel.md` — OTel setup for Workers
- `opentelemetry-baggage-propagation.md` — W3C baggage for non-span metadata
- `w3c-trace-context-propagation.md` — traceparent/tracestate header semantics
- `cloudflare-analytics-engine.md` — custom metrics from Workers
- `queue-depth-monitoring.md` — monitoring queue backlog depth

## Sources

- Cloudflare Queues developer docs: https://developers.cloudflare.com/queues/
- W3C Trace Context specification: https://www.w3.org/TR/trace-context/
- OpenTelemetry JS propagation API: https://opentelemetry.io/docs/languages/js/propagation/
- Cloudflare Queues message batching: https://developers.cloudflare.com/queues/reference/batching-retries/
