# Bulkhead Pattern for Concurrency Isolation in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A slow payment gateway causes Workers to pile up waiting for responses. The queue of in-flight requests grows until memory pressure causes the runtime to shed load indiscriminately, taking down the inventory and email paths alongside payment — services that were healthy before the cascade began.

## Context

The bulkhead pattern partitions concurrency capacity the same way watertight compartments partition a ship: a breach in one compartment does not flood the others. In a Workers environment, you implement bulkheads as Durable Objects acting as semaphores. Each downstream service gets its own DO. The DO tracks the count of in-flight slots; when the cap is reached it rejects new requests with 503 immediately rather than letting them queue indefinitely.

This approach gives you:
- Hard per-service concurrency limits enforced at the edge.
- Fast-fail behaviour under load — callers get a 503 they can handle, not a timeout.
- Per-bulkhead utilisation metrics via Workers Analytics Engine.

## Bulkhead Durable Object

```typescript
// bulkhead.ts
export interface BulkheadConfig {
  maxSlots: number;
  serviceId: string;
}

export class Bulkhead implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const serviceId = url.searchParams.get('service') ?? 'unknown';
    const maxSlots = Number(url.searchParams.get('max') ?? '10');

    if (url.pathname === '/acquire') {
      return this.acquire(serviceId, maxSlots);
    }
    if (url.pathname === '/release') {
      return this.release(serviceId);
    }
    if (url.pathname === '/stats') {
      return this.stats(serviceId);
    }
    return new Response('not found', { status: 404 });
  }

  private async acquire(serviceId: string, maxSlots: number): Promise<Response> {
    const key = `slots:${serviceId}`;
    const current = (await this.state.storage.get<number>(key)) ?? 0;

    if (current >= maxSlots) {
      this.recordMetric(serviceId, 'rejected', current, maxSlots);
      return new Response(
        JSON.stringify({ error: 'bulkhead_full', service: serviceId, slots: current, max: maxSlots }),
        { status: 503, headers: { 'Content-Type': 'application/json', 'Retry-After': '1' } }
      );
    }

    await this.state.storage.put(key, current + 1);
    this.recordMetric(serviceId, 'acquired', current + 1, maxSlots);
    return Response.json({ acquired: true, slots: current + 1, max: maxSlots });
  }

  private async release(serviceId: string): Promise<Response> {
    const key = `slots:${serviceId}`;
    const current = (await this.state.storage.get<number>(key)) ?? 0;
    const next = Math.max(0, current - 1);
    await this.state.storage.put(key, next);
    this.recordMetric(serviceId, 'released', next, -1);
    return Response.json({ released: true, slots: next });
  }

  private async stats(serviceId: string): Promise<Response> {
    const key = `slots:${serviceId}`;
    const current = (await this.state.storage.get<number>(key)) ?? 0;
    return Response.json({ service: serviceId, slots: current });
  }

  private recordMetric(
    serviceId: string,
    event: 'acquired' | 'released' | 'rejected',
    slots: number,
    max: number
  ): void {
    this.env.ANALYTICS.writeDataPoint({
      blobs: [serviceId, event],
      doubles: [slots, max],
      indexes: [serviceId],
    });
  }
}
```

## Worker Integration Helper

Wrap downstream calls with a bulkhead guard. Acquire a slot before calling the downstream service and release it in a `finally` block.

```typescript
// bulkhead-guard.ts
interface BulkheadOptions {
  service: string;
  maxSlots: number;
  bulkheadDO: DurableObjectNamespace;
}

export async function withBulkhead<T>(
  options: BulkheadOptions,
  fn: () => Promise<T>
): Promise<T> {
  const id = options.bulkheadDO.idFromName(options.service);
  const stub = options.bulkheadDO.get(id);

  const acquireRes = await stub.fetch(
    `https://bulkhead/acquire?service=${options.service}&max=${options.maxSlots}`,
    { method: 'POST' }
  );

  if (acquireRes.status === 503) {
    const body = await acquireRes.json<{ error: string; service: string }>();
    throw Object.assign(new Error(`Bulkhead full for service: ${body.service}`), {
      status: 503,
      service: body.service,
    });
  }

  try {
    return await fn();
  } finally {
    await stub.fetch(
      `https://bulkhead/release?service=${options.service}`,
      { method: 'POST' }
    );
  }
}
```

## Usage Across Multiple Services

```typescript
// worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/checkout') {
      const body = await request.json<{ orderId: string; amount: number }>();

      let chargeResult: unknown;
      try {
        chargeResult = await withBulkhead(
          { service: 'payment', maxSlots: 20, bulkheadDO: env.BULKHEAD },
          () => callPaymentService(body.orderId, body.amount, env)
        );
      } catch (err: any) {
        if (err.status === 503) {
          return Response.json(
            { error: 'payment_service_busy', retryAfter: 1 },
            { status: 503 }
          );
        }
        throw err;
      }

      let reserveResult: unknown;
      try {
        reserveResult = await withBulkhead(
          { service: 'inventory', maxSlots: 50, bulkheadDO: env.BULKHEAD },
          () => callInventoryService(body.orderId, env)
        );
      } catch (err: any) {
        if (err.status === 503) {
          return Response.json(
            { error: 'inventory_service_busy', retryAfter: 1 },
            { status: 503 }
          );
        }
        throw err;
      }

      return Response.json({ chargeResult, reserveResult });
    }

    return new Response('not found', { status: 404 });
  },
};

async function callPaymentService(orderId: string, amount: number, env: Env) {
  const res = await fetch(`${env.PAYMENT_SERVICE_URL}/charge`, {
    method: 'POST',
    body: JSON.stringify({ orderId, amount }),
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`payment failed: ${res.status}`);
  return res.json();
}

async function callInventoryService(orderId: string, env: Env) {
  const res = await fetch(`${env.INVENTORY_SERVICE_URL}/reserve`, {
    method: 'POST',
    body: JSON.stringify({ orderId }),
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`inventory failed: ${res.status}`);
  return res.json();
}
```

## Querying Utilisation via Analytics Engine

```typescript
// Read bulkhead utilisation from Analytics Engine GraphQL API
const query = `{
  viewer {
    accounts(filter: { accountTag: $accountId }) {
      workersAnalyticsEngineAdaptiveGroups(
        limit: 10
        filter: { datetime_geq: "2026-08-24T00:00:00Z", index1: "payment" }
        orderBy: [datetime_DESC]
      ) {
        sum { count }
        avg { double1 }
        dimensions { blob1 blob2 }
      }
    }
  }
}`;
```

## Anti-patterns

- **Global semaphore across all services** — one DO for everything defeats the isolation goal. A full payment bulkhead should not block inventory calls.
- **Slot leak on uncaught exceptions** — always release in a `finally` block. An acquired slot that is never released will permanently reduce capacity until the DO storage is manually corrected.
- **Setting `maxSlots` too high** — a limit of 1000 offers no protection. Profile your downstream service's saturation point under load and set `maxSlots` to 70-80% of that ceiling.
- **Ignoring 503 from the bulkhead** — callers must handle 503 with appropriate backoff or queue-based retry, not by retrying immediately in a tight loop.

## Gotchas

- Durable Objects process one request at a time. The acquire/release cycle adds a round-trip to your critical path. Keep downstream calls outside the DO — only the slot counter lives in the DO.
- A DO restart resets in-memory state but not storage. The slot counter persists across restarts, so a crash mid-request may leave a slot permanently acquired. Add a periodic alarm that resets the counter to zero if it has not moved in N seconds.
- The Analytics Engine `writeDataPoint` method is fire-and-forget; it will not throw on failure. Do not rely on it for control flow.

## Verification

```bash
# Check current slot utilisation
curl https://<worker>.workers.dev/bulkhead/stats?service=payment
# Expected: {"service":"payment","slots":3}

# Saturate the bulkhead (run 21 parallel requests against maxSlots=20)
for i in $(seq 1 21); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://<worker>.workers.dev/checkout \
    -H 'Content-Type: application/json' \
    -d '{"orderId":"ord-'$i'","amount":100}' &
done
wait
# At least one response should be 503
```

## Related

- `saga-pattern-workers-durable-objects-compensation.md`
- `cqrs-workers-d1-read-write-separation.md`
- `strangler-fig-workers-legacy-api-migration.md`

## Sources

- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- Cloudflare Workers Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Michael T. Nygard, *Release It!*, Chapter 5 — Stability Patterns
