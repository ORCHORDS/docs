# Correlation ID Propagation Across Workers Services

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

An HTTP request enters the edge at `api.example.com`, is forwarded to a pricing
Worker via service binding, which calls an inventory Worker, which queries D1
and sends a queue message that triggers a fulfillment Worker. When something goes
wrong, your logs show errors from `inventory-worker` and `fulfillment-worker`
with no way to connect them to the original user request. Debugging requires
manually cross-referencing timestamps and guessing which calls are related.

---

## Context

A **correlation ID** is a unique identifier that is attached to a request at
the entry point and propagated to every downstream call, log statement, and
queued message. All telemetry that shares a correlation ID belongs to the same
logical operation, making it trivial to reconstruct the full call tree across
services.

In Cloudflare Workers, propagation must be explicit — there is no automatic
context propagation framework. You carry the correlation ID through:

- HTTP headers (`X-Correlation-Id` or `traceparent` for W3C Trace Context)
- Service binding `Request` objects
- Queue message bodies
- Durable Object `fetch()` calls
- Structured log fields

This pattern is a prerequisite for effective distributed tracing. Without it,
`distributed-tracing-otel.md` cannot correlate spans across Workers.

---

## Generating the Correlation ID at the Entry Point

```typescript
// src/middleware/correlation.ts
import { randomUUID } from 'crypto';

export const CORRELATION_HEADER = 'x-correlation-id';
export const REQUEST_ID_HEADER = 'x-request-id';

/**
 * Extract or generate a correlation ID.
 * Trusts an incoming x-correlation-id from internal callers;
 * generates a fresh one for external (untrusted) requests.
 */
export function extractOrGenerate(
  request: Request,
  options: { trustIncoming?: boolean } = {},
): string {
  if (options.trustIncoming) {
    const incoming = request.headers.get(CORRELATION_HEADER);
    if (incoming && isValidCorrelationId(incoming)) {
      return incoming;
    }
  }
  // Always generate a fresh ID for public-facing entry points
  return randomUUID();
}

function isValidCorrelationId(id: string): boolean {
  // Accept UUIDs and W3C traceparent formats
  return /^[0-9a-f-]{36}$/.test(id) || /^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/.test(id);
}
```

---

## Entry Point Worker: Attach and Forward

```typescript
// src/index.ts — public-facing API Worker

import { extractOrGenerate, CORRELATION_HEADER } from './middleware/correlation';
import { createLogger } from './lib/logger';
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Generate a fresh correlation ID for every inbound public request
    const correlationId = extractOrGenerate(request, { trustIncoming: false });

    // Attach to all log statements in this Worker
    const log = createLogger({ correlationId, service: 'api-gateway' });
    log.info('request received', { method: request.method, url: request.url });

    try {
      const response = await routeRequest(request, correlationId, env);

      // Echo the correlation ID back to the client for client-side logging
      response.headers.set(CORRELATION_HEADER, correlationId);
      return response;

    } catch (err) {
      log.error('unhandled error', { error: String(err) });
      return new Response('Internal Server Error', {
        status: 500,
        headers: { [CORRELATION_HEADER]: correlationId },
      });
    }
  },
};

async function routeRequest(
  request: Request,
  correlationId: string,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname.startsWith('/products')) {
    // Forward to pricing-worker via service binding, carrying the correlation ID
    return forwardToService(request, correlationId, env.PRICING_WORKER);
  }

  return new Response('Not Found', { status: 404 });
}

function forwardToService(
  original: Request,
  correlationId: string,
  service: Fetcher,
): Promise<Response> {
  // Rebuild the request with the correlation ID header added
  const downstream = new Request(original, {
    headers: mergeHeaders(original.headers, {

    }),
  });
  return service.fetch(downstream);
}

function mergeHeaders(
  base: Headers,
  extra: Record<string, string>,
): Headers {
  const merged = new Headers(base);
  for (const [k, v] of Object.entries(extra)) {
    merged.set(k, v);
  }
  return merged;
}
```

---

## Downstream Worker: Trust and Re-propagate

```typescript
// src/workers/pricing-worker/index.ts

import { extractOrGenerate, CORRELATION_HEADER } from '../../middleware/correlation';
import { createLogger } from '../../lib/logger';
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Trust the correlation ID from the internal caller (service binding)
    const correlationId = extractOrGenerate(request, { trustIncoming: true });
    const log = createLogger({ correlationId, service: 'pricing-worker' });

    log.info('pricing request received', { url: request.url });

    // Forward to inventory worker, still carrying the same correlation ID
    const inventoryRes = await env.INVENTORY_WORKER.fetch(
      new Request('https://internal/stock', {
        headers: { [CORRELATION_HEADER]: correlationId },
      })
    );

    const inventory = await inventoryRes.json();
    log.info('inventory fetched', { inStock: (inventory as any).available });

    return Response.json({ price: 9999, correlationId });
  },
};
```

---

## Propagation Through Cloudflare Queues

Queue messages do not have headers. Embed the correlation ID in the message
body itself:

```typescript
// Producer: embed correlationId in the message body
await env.EVENTS_QUEUE.send({
  correlationId,           // <-- carry it explicitly
  id: randomUUID(),
  type: 'order.paid',
  aggregateId: orderId,
  payload: { orderId },
});

// Consumer: extract from body
export default {
  async queue(batch: MessageBatch<EventMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const { correlationId } = message.body;
      const log = createLogger({ correlationId, service: 'fulfillment-consumer' });
      log.info('processing event', { type: message.body.type });

      await processEvent(message.body, log, env);
      message.ack();
    }
  },
};
```

---

## Structured Logger with Correlation ID Binding

```typescript
// src/lib/logger.ts

interface LogContext {
  correlationId: string;
  service: string;

}

interface Logger {
  info(message: string, extra?: Record<string, unknown>): void;
  warn(message: string, extra?: Record<string, unknown>): void;
  error(message: string, extra?: Record<string, unknown>): void;
}

export function createLogger(context: LogContext): Logger {
  const base = {
    timestamp: () => new Date().toISOString(),
    ...context,
  };

  function log(level: string, message: string, extra?: Record<string, unknown>) {
    console.log(JSON.stringify({
      level,
      message,
      ...base,
      timestamp: new Date().toISOString(),
      ...extra,
    }));
  }

  return {
    info:  (msg, extra) => log('INFO',  msg, extra),
    warn:  (msg, extra) => log('WARN',  msg, extra),
    error: (msg, extra) => log('ERROR', msg, extra),
  };
}
```

With this logger, every log line includes `correlationId` and `service`, making
it trivial to filter all log lines for a single operation:

```bash
# Tail logs and filter by correlation ID
wrangler tail api-gateway | grep '"correlationId":"550e8400-e29b-41d4-a716-446655440000"'
```

---

## W3C Trace Context (`traceparent`)

For compatibility with OpenTelemetry-aware infrastructure, use `traceparent`
instead of a custom header. The format encodes trace ID, span ID, and flags:

```
traceparent: 00-{traceId:32hex}-{spanId:16hex}-{flags:2hex}
```

```typescript
function generateTraceParent(): { traceId: string; spanId: string; traceparent: string } {
  const traceId = crypto.randomUUID().replace(/-/g, '');
  const spanId  = crypto.randomUUID().replace(/-/g, '').slice(0, 16);
  return {
    traceId,
    spanId,
    traceparent: `00-${traceId}-${spanId}-01`,
  };
}

function parseTraceParent(header: string): { traceId: string; spanId: string } | null {
  const parts = header.split('-');
  if (parts.length !== 4 || parts[0] !== '00') return null;
  return { traceId: parts[1], spanId: parts[2] };
}
```

When forwarding to a child span, generate a new `spanId` but preserve the
`traceId` to keep all spans in the same trace.

---

## Anti-patterns

**Trusting `x-correlation-id` from external callers without validation**
A malicious client can inject a crafted correlation ID to poison logs or
impersonate another request. Always generate a fresh ID at the public edge;
only trust the header from internal service-binding callers behind your own
authentication layer.

**Using short or non-unique IDs**
Sequential integers or short hashes collide in distributed systems. Always use
UUID v4 (128 bits of randomness) or `traceparent`-format IDs.

**Embedding the correlation ID only in some log lines**
The value of the pattern comes from consistency — every single log statement,
including errors, database queries, and external calls, must include the
correlation ID. Bind it to the logger at construction time, not at call sites.

**Dropping the correlation ID at queue boundaries**
Queue messages have no headers. Developers often forget to include the
correlation ID in the message body. Make it a required field in all message
schemas.

---

## Gotchas

- **Workers do not share in-process state**: There is no equivalent of a Node.js
  `AsyncLocalStorage` or Go `context.Context` that flows automatically. Every
  function that logs or calls downstream must receive `correlationId` explicitly
  as a parameter.

- **Cloudflare Tail Workers** receive a copy of every log line from a Worker.
  If you use a Tail Worker to ship logs to an external system, ensure it
  preserves and indexes the `correlationId` field.

- **UUID generation cost**: `crypto.randomUUID()` is fast (< 0.1 ms) but not
  free. Call it once per request at the entry point and pass the string
  downstream — never call it inside a hot loop.

- **Log storage in `wrangler tail`**: `wrangler tail` is a stream of real-time
  events and does not persist logs. For correlation ID–based debugging in
  production, ship logs to an external store (Logpush → R2, Logpush → a SIEM).

---

## Verification

```bash
# 1. Send a request and capture the correlation ID from the response header
CORR_ID=$(curl -si https://api.example.com/products/prod_123 \
  | grep -i x-correlation-id | awk '{print $2}' | tr -d '\r')
echo "Correlation ID: $CORR_ID"

# 2. Search across service logs for that ID
wrangler tail api-gateway         | grep "$CORR_ID" &
wrangler tail pricing-worker      | grep "$CORR_ID" &
wrangler tail inventory-worker    | grep "$CORR_ID" &
wrangler tail fulfillment-consumer | grep "$CORR_ID" &

# Re-run the request
curl https://api.example.com/products/prod_123

# 3. Verify all services emit the same correlation ID in their logs
```

---

## Related

- `distributed-tracing-otel.md` — extends correlation IDs to full spans with
  timing, parent-child relationships, and export to Jaeger / Honeycomb.
- `structured-logging-detail.md` — the structured log format that hosts the
  `correlationId` field.
- `scatter-gather-parallel-workers.md` — a scenario where one correlation ID must
  be fanned out to N simultaneous subrequests.
- `feature-observability-tracing.md` — observability strategy that depends on
  correlation IDs for cross-service request reconstruction.
- `error-handling-strategies.md` — returning the correlation ID in error
  responses so clients can reference it in support tickets.

---

## Sources

- W3C Trace Context specification:
  https://www.w3.org/TR/trace-context/
- OpenTelemetry propagation concepts:
  https://opentelemetry.io/docs/concepts/context-propagation/
- Cloudflare Workers Tail Workers:
  https://developers.cloudflare.com/workers/observability/tail-workers/
- Cloudflare Logpush:
  https://developers.cloudflare.com/logs/about/
- MDN — crypto.randomUUID():
  https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID
