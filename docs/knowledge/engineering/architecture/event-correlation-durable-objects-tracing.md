# Event Correlation with Durable Objects and Distributed Tracing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A example project platform request fans out across five Workers, two Queue consumers, and a Durable Object
alarm — then a user reports the payment failed. The logs show five different request IDs, the Queue
consumer has its own trace, and the Durable Object alarm ran in a separate invocation context
entirely. Reconstructing the causal chain to answer "what happened to order #ORD-7829?" requires
manually grepping across multiple log streams with no guarantee of completeness.

Event correlation solves this by: (1) propagating a stable `correlationId` across all hops,
(2) recording a causal graph of span parent→child relationships inside a Durable Object, and
(3) emitting structured trace events to Analytics Engine for offline querying.

## Context

Cloudflare does not natively propagate W3C Trace Context headers through Queue messages, Service
Binding calls, or Durable Object alarm invocations. You must carry the correlation context
explicitly. A Durable Object — one per correlation ID, addressed by the ID itself — is the natural
home for the mutable span registry because it serialises concurrent span writes without distributed
locking.

---

## Correlation ID Propagation Primitives

```typescript
// packages/shared-kernel/src/correlation.ts

export interface TraceContext {
  correlationId: string;   // stable across the full request tree
  spanId:        string;   // unique per invocation hop
  parentSpanId?: string;   // spanId of the caller
  traceFlags:    number;   // W3C trace-flags byte (01 = sampled)
}

/** Parse a W3C traceparent header into a TraceContext */
export function parseTraceparent(header: string): TraceContext | null {
  // version-trace_id-parent_id-flags
  const match = header.match(/^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/i);
  if (!match) return null;
  return {
    correlationId: match[1],
    spanId:        match[2],
    parentSpanId:  undefined,
    traceFlags:    parseInt(match[3], 16),
  };
}

/** Format a TraceContext as a W3C traceparent header value */
export function formatTraceparent(ctx: TraceContext): string {
  return `00-${ctx.correlationId}-${ctx.spanId}-${ctx.traceFlags.toString(16).padStart(2, '0')}`;
}

/** Create a child span derived from a parent context */
export function childSpan(parent: TraceContext, newSpanId: string): TraceContext {
  return {
    correlationId: parent.correlationId,
    spanId:        newSpanId,
    parentSpanId:  parent.spanId,
    traceFlags:    parent.traceFlags,
  };
}

/** Generate a random 16-hex-character span ID */
export function newSpanId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(8)))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/** Generate a random 32-hex-character correlation/trace ID */
export function newCorrelationId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

---

## Correlation Durable Object — Span Registry

```typescript
// workers/tracing/src/correlation-do.ts
import { DurableObject } from 'cloudflare:workers';
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';

interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

export interface SpanRecord {
  spanId:       string;
  parentSpanId: string | null;
  workerName:   string;
  operation:    string;
  startedAt:    number;  // ms epoch
  finishedAt?:  number;
  status:       'pending' | 'ok' | 'error';
  metadata?:    Record<string, string>;
}

export class CorrelationDO extends DurableObject<Env> {
  private spans = new Map<string, SpanRecord>();

  async startSpan(span: SpanRecord): Promise<void> {
    this.spans.set(span.spanId, span);
    await this.ctx.storage.put(`span:${span.spanId}`, span);

    // Emit to Analytics Engine (no await — fire and forget)
    this.env.ANALYTICS.writeDataPoint({
      blobs:    [span.correlationId ?? '', span.spanId, span.parentSpanId ?? '', span.workerName, span.operation, 'start'],
      doubles:  [span.startedAt],
      indexes:  [span.spanId],
    } as any);
  }

  async endSpan(
    spanId: string,
    status: 'ok' | 'error',
    metadata?: Record<string, string>,
  ): Promise<void> {
    const span = this.spans.get(spanId)
      ?? await this.ctx.storage.get<SpanRecord>(`span:${spanId}`);

    if (!span) return;

    const finished: SpanRecord = {
      ...span,
      finishedAt: Date.now(),
      status,
      metadata: { ...(span.metadata ?? {}), ...(metadata ?? {}) },
    };
    this.spans.set(spanId, finished);
    await this.ctx.storage.put(`span:${spanId}`, finished);

    this.env.ANALYTICS.writeDataPoint({
      blobs:   [span.correlationId ?? '', spanId, span.parentSpanId ?? '', span.workerName, span.operation, status],
      doubles: [span.startedAt, finished.finishedAt!],
      indexes: [spanId],
    } as any);
  }

  async getTrace(): Promise<SpanRecord[]> {
    const all = await this.ctx.storage.list<SpanRecord>({ prefix: 'span:' });
    return Array.from(all.values());
  }

  // Self-clean after 24 hours via alarm
  async alarm(): Promise<void> {
    await this.ctx.storage.deleteAll();
  }

  async scheduleCleanup(): Promise<void> {
    await this.ctx.storage.setAlarm(Date.now() + 24 * 60 * 60 * 1000);
  }
}
```

---

## Tracing Service Worker — RPC Surface

```typescript
// workers/tracing/src/index.ts
import { WorkerEntrypoint } from 'cloudflare:workers';
import { CorrelationDO } from './correlation-do';
import type { SpanRecord } from './correlation-do';

interface Env {
  CORRELATION_DO: DurableObjectNamespace;
}

export class TracingService extends WorkerEntrypoint<Env> {
  private stub(correlationId: string) {
    const id = this.env.CORRELATION_DO.idFromName(correlationId);
    return this.env.CORRELATION_DO.get(id);
  }

  async startSpan(correlationId: string, span: SpanRecord): Promise<void> {
    await this.stub(correlationId).startSpan(span);
  }

  async endSpan(
    correlationId: string,
    spanId: string,
    status: 'ok' | 'error',
    metadata?: Record<string, string>,
  ): Promise<void> {
    await this.stub(correlationId).endSpan(spanId, status, metadata);
  }

  async getTrace(correlationId: string): Promise<SpanRecord[]> {
    return this.stub(correlationId).getTrace();
  }
}

export { CorrelationDO };

export default {
  fetch(): Response {
    return new Response('Tracing RPC only', { status: 405 });
  },
};
```

---

## Instrumenting a Worker Hop

```typescript
// workers/billing/src/index.ts — instrumented handler
import {
  parseTraceparent,
  formatTraceparent,
  childSpan,
  newSpanId,
  newCorrelationId,
  type TraceContext,
} from '@example project/shared-kernel/correlation';
import type { TracingService } from '../../tracing/src/index';

interface Env {
  TRACING: Service<TracingService>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const incomingHeader = request.headers.get('traceparent');
    const parentCtx: TraceContext = incomingHeader
      ? parseTraceparent(incomingHeader) ?? {
          correlationId: newCorrelationId(),
          spanId: newSpanId(),
          traceFlags: 1,
        }
      : { correlationId: newCorrelationId(), spanId: newSpanId(), traceFlags: 1 };

    const mySpanId = newSpanId();
    const myCtx = childSpan(parentCtx, mySpanId);

    await env.TRACING.startSpan(myCtx.correlationId, {
      spanId:       mySpanId,
      parentSpanId: myCtx.parentSpanId ?? null,
      workerName:   'example project-billing',
      operation:    `${request.method} ${new URL(request.url).pathname}`,
      startedAt:    Date.now(),
      status:       'pending',
    });

    try {
      // ... actual billing logic ...
      const result = await processBilling(request, env, myCtx);

      await env.TRACING.endSpan(myCtx.correlationId, mySpanId, 'ok');
      return result;
    } catch (err) {
      await env.TRACING.endSpan(myCtx.correlationId, mySpanId, 'error', {
        error: String(err),
      });
      throw err;
    }
  },
};
```

---

## Propagating Correlation Through Queues

Queue messages do not carry HTTP headers. Embed the trace context in the message body:

```typescript
// workers/order/src/index.ts — Queue producer
interface OrderMessage {
  orderId:       string;
  amount:        number;
  traceContext:  { correlationId: string; spanId: string; traceFlags: number };
}

async function enqueueOrder(
  queue: Queue<OrderMessage>,
  orderId: string,
  amount: number,
  ctx: TraceContext,
): Promise<void> {
  await queue.send({
    orderId,
    amount,
    traceContext: {
      correlationId: ctx.correlationId,
      spanId:        ctx.spanId,
      traceFlags:    ctx.traceFlags,
    },
  });
}

// workers/order-consumer/src/index.ts — Queue consumer
export default {
  async queue(batch: MessageBatch<OrderMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const parentCtx: TraceContext = {
        ...msg.body.traceContext,
        parentSpanId: msg.body.traceContext.spanId,
      };
      const mySpanId = newSpanId();
      const myCtx = childSpan(parentCtx, mySpanId);

      await env.TRACING.startSpan(myCtx.correlationId, {
        spanId:       mySpanId,
        parentSpanId: myCtx.parentSpanId ?? null,
        workerName:   'example project-order-consumer',
        operation:    'process-order',
        startedAt:    Date.now(),
        status:       'pending',
      });

      try {
        await processOrder(msg.body, env);
        await env.TRACING.endSpan(myCtx.correlationId, mySpanId, 'ok');
        msg.ack();
      } catch (err) {
        await env.TRACING.endSpan(myCtx.correlationId, mySpanId, 'error', { error: String(err) });
        msg.retry();
      }
    }
  },
};
```

---

## Querying Traces from Analytics Engine

```sql
-- Analytics Engine SQL API query (via Cloudflare API or Workers Analytics Engine binding)
SELECT
  blob1  AS correlation_id,
  blob2  AS span_id,
  blob3  AS parent_span_id,
  blob4  AS worker_name,
  blob5  AS operation,
  blob6  AS event_type,
  double1 AS started_at_ms,
  double2 AS finished_at_ms,
  (double2 - double1) AS duration_ms
FROM spans_dataset
WHERE blob1 = 'a3f9...correlation_id_here...'
ORDER BY double1 ASC;
```

---

## Anti-patterns

- **Using `request.id` (Cloudflare's auto-assigned ID) as the correlation ID**: This ID is
  per-Worker-invocation, not per-user-request. A Queue consumer runs in a separate invocation with a
  different `request.id`. Always generate and propagate your own `correlationId`.
- **Creating one DO per span instead of one DO per correlationId**: This results in thousands of DO
  instances per request fan-out. One DO per correlationId serialises writes and keeps the span graph
  co-located.
- **Blocking the critical path on `endSpan`**: If the billing outcome has already been returned to
  the user, fire `endSpan` with `ctx.waitUntil()` to avoid adding tracing latency to the response.
- **Storing unbounded metadata in span records**: Limit `metadata` values to short strings (< 256
  chars). Large payloads (stack traces) should be written to R2 with a reference stored in the span.
- **Not scheduling the cleanup alarm**: Correlation DOs accumulate indefinitely without `scheduleCleanup()`.
  Call it in `startSpan` the first time a DO is created (check storage length = 0).

---

## Gotchas

- Durable Object Storage `list()` with a `prefix:` filter streams results lazily; for a trace with
  > 128 spans you must paginate using the `cursor` option.
- Analytics Engine `writeDataPoint` is fire-and-forget and may be lost if the Worker is evicted
  before the event is flushed. Use `ctx.waitUntil()` when reliability is critical.
- Service Binding calls to the Tracing Worker count toward the calling Worker's subrequest budget
  (1000 subrequests per request on the paid plan). High-fan-out pipelines may exhaust the budget if
  every micro-step emits a start+end span via RPC. Batch span updates where possible.
- W3C `traceparent` uses a 32-hex trace-ID and 16-hex parent-ID. `crypto.getRandomValues` on 16
  bytes gives 32 hex chars. Do not use `Math.random()` — it is not cryptographically uniform.
- When a DO alarm fires, the `TraceContext` is no longer available in the request scope. The alarm
  handler must read `correlationId` from DO storage to emit a span for alarm-triggered work.

---

## Verification

```typescript
// test/correlation.test.ts
import { describe, it, expect } from 'vitest';
import {
  parseTraceparent,
  formatTraceparent,
  childSpan,
  newSpanId,
  newCorrelationId,
} from '../packages/shared-kernel/src/correlation';

describe('Correlation primitives', () => {
  it('round-trips a traceparent header', () => {
    const correlationId = newCorrelationId();
    const spanId = newSpanId();
    const ctx = { correlationId, spanId, traceFlags: 1 };
    const header = formatTraceparent(ctx);
    const parsed = parseTraceparent(header);
    expect(parsed?.correlationId).toBe(correlationId);
    expect(parsed?.spanId).toBe(spanId);
  });

  it('childSpan preserves correlationId and sets parentSpanId', () => {
    const parent = { correlationId: newCorrelationId(), spanId: newSpanId(), traceFlags: 1 };
    const child  = childSpan(parent, newSpanId());
    expect(child.correlationId).toBe(parent.correlationId);
    expect(child.parentSpanId).toBe(parent.spanId);
  });
});
```

End-to-end: trigger a multi-Worker flow, then call `GET /trace/:correlationId` on the Tracing
Worker and verify the span tree is complete and acyclic.

---

## Related

- `/documentation/docs/policies/architecture/correlation-id-propagation-workers-service-bindings.md`
- `/documentation/docs/policies/architecture/distributed-tracing-architecture.md`
- `/documentation/docs/policies/architecture/workers-tail-handlers-observability.md`
- `/documentation/docs/policies/architecture/analytics-engine-event-pipeline.md`
- `/documentation/docs/policies/architecture/durable-objects-workflow-state-machine.md`

---

## Sources

- W3C Trace Context spec: https://www.w3.org/TR/trace-context/
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- OpenTelemetry specification — Span relationships: https://opentelemetry.io/docs/reference/specification/overview/
