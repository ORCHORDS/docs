# Bulkhead Pattern — Limiting Concurrent Calls with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A single slow dependency (a third-party payment API, a rate-limited data provider) is brought down by a burst of concurrent Workers, causing cascading failures across the entire application. You need a hard ceiling on how many in-flight requests reach that dependency at any given time, with excess requests queued rather than dropped.

---

## Context

The bulkhead pattern isolates a resource pool so that overload in one area cannot exhaust shared capacity. A Durable Object maintains a semaphore counter in persistent storage and serializes all acquire/release calls through its single-threaded execution model. Workers call the bulkhead DO before touching the dependency and release the slot afterwards. A configurable `maxConcurrent` cap and a `timeoutMs` for waiting requests give operators knobs to tune per-dependency. Because DO requests are queued and serialized natively, the implementation avoids race conditions without locks.

---

## Schema — Bulkhead Config (wrangler.toml)

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
BULKHEAD_MAX_CONCURRENT = "10"
BULKHEAD_TIMEOUT_MS     = "5000"

[[durable_objects.bindings]]
name       = "BULKHEAD"
class_name = "BulkheadDO"

[[migrations]]
tag   = "v1"
new_classes = ["BulkheadDO"]

[[services]]
binding  = "PAYMENT_API"
service  = "payment-api-worker"
```

---

## Implementation — Bulkhead Durable Object

```typescript
// src/durable-objects/bulkhead.ts
import { DurableObject } from 'cloudflare:workers';

interface BulkheadConfig {
  maxConcurrent: number;
  timeoutMs: number;
}

interface WaitingRequest {
  resolve: (granted: boolean) => void;
  timer: ReturnType<typeof setTimeout>;
}

export class BulkheadDO extends DurableObject {
  private inflight = 0;
  private readonly waitQueue: WaitingRequest[] = [];

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const maxConcurrent = parseInt(url.searchParams.get('max') ?? '10', 10);
    const timeoutMs = parseInt(url.searchParams.get('timeout') ?? '5000', 10);

    if (url.pathname === '/acquire') {
      return this.acquire({ maxConcurrent, timeoutMs });
    }
    if (url.pathname === '/release') {
      return this.release();
    }
    if (url.pathname === '/status') {
      return Response.json({
        inflight: this.inflight,
        waiting: this.waitQueue.length,
        maxConcurrent,
      });
    }
    return new Response('Not found', { status: 404 });
  }

  private async acquire(config: BulkheadConfig): Promise<Response> {
    if (this.inflight < config.maxConcurrent) {
      this.inflight++;
      return Response.json({ granted: true, inflight: this.inflight });
    }

    // Queue the request and wait for a slot
    const granted = await new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => {
        const idx = this.waitQueue.findIndex((w) => w.resolve === resolve);
        if (idx !== -1) this.waitQueue.splice(idx, 1);
        resolve(false); // timeout — not granted
      }, config.timeoutMs);

      this.waitQueue.push({ resolve, timer });
    });

    if (!granted) {
      return Response.json(
        { granted: false, reason: 'timeout' },
        { status: 429 },
      );
    }

    this.inflight++;
    return Response.json({ granted: true, inflight: this.inflight });
  }

  private release(): Response {
    if (this.inflight > 0) this.inflight--;

    // Wake the oldest waiting request
    if (this.waitQueue.length > 0) {
      const next = this.waitQueue.shift()!;
      clearTimeout(next.timer);
      next.resolve(true);
    }

    return Response.json({ released: true, inflight: this.inflight });
  }
}
```

---

## Implementation — Bulkhead Client Helper

```typescript
// src/lib/bulkhead-client.ts
import { Env } from '../types';

export async function withBulkhead<T>(
  env: Env,
  key: string,
  fn: () => Promise<T>,
  options: { maxConcurrent?: number; timeoutMs?: number } = {},
): Promise<T> {
  const maxConcurrent = options.maxConcurrent ?? parseInt(env.BULKHEAD_MAX_CONCURRENT, 10);
  const timeoutMs = options.timeoutMs ?? parseInt(env.BULKHEAD_TIMEOUT_MS, 10);

  const id = env.BULKHEAD.idFromName(key);
  const stub = env.BULKHEAD.get(id);

  const acquireParams = new URLSearchParams({
    max: String(maxConcurrent),
    timeout: String(timeoutMs),
  });

  const acquireRes = await stub.fetch(
    new Request(`https://bulkhead/acquire?${acquireParams}`),
    { method: 'GET' },
  );
  const { granted, reason } = await acquireRes.json<{ granted: boolean; reason?: string }>();

  if (!granted) {
    throw Object.assign(new Error(`Bulkhead [${key}] rejected: ${reason}`), {
      status: 429,
      bulkheadKey: key,
    });
  }

  try {
    return await fn();
  } finally {
    // Always release — even on error
    await stub.fetch(new Request('https://bulkhead/release'), { method: 'GET' });
  }
}
```

---

## Integration — Worker Using the Bulkhead

```typescript
// src/handlers/charge.ts
import { withBulkhead } from '../lib/bulkhead-client';
import { Env } from '../types';

export async function handleCharge(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{ userId: string; amountCents: number }>();

  try {
    const result = await withBulkhead(
      env,
      'payment-api', // bulkhead key — one DO per dependency
      async () => {
        const res = await env.PAYMENT_API.fetch('/charge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`payment failed: ${res.status}`);
        return res.json();
      },
      { maxConcurrent: 10, timeoutMs: 5000 },
    );
    return Response.json(result);
  } catch (err: any) {
    if (err.status === 429) {
      return Response.json({ error: 'service busy, try again' }, { status: 429 });
    }
    return Response.json({ error: err.message }, { status: 502 });
  }
}
```

---

## Anti-patterns

- **Using a KV counter for the semaphore** — KV has eventual consistency; two Workers can read the same value and both increment past the cap; DO single-threaded execution is the correct primitive.
- **Never releasing on error** — always wrap the dependency call in `try/finally` so the slot is released even when the downstream throws.
- **One global bulkhead for all dependencies** — defeats isolation; create one DO name per dependency (`payment-api`, `inventory-api`, etc.).
- **Setting `maxConcurrent` too low** — starves legitimate traffic; baseline with P99 response times and capacity tests before tuning.

---

## Gotchas

- The DO in-memory `inflight` counter resets on eviction; slots that were acquired before eviction become orphaned. Add a short `ctx.storage.setAlarm()` watchdog to reset the counter if it diverges from zero after a quiet period.
- Workers Durable Objects bill per request; at very high RPS the per-acquire/release pair can dominate cost — consider batching multiple permits in one call.
- The wait queue is also in-memory; a DO eviction during heavy contention drops all waiting promises. Callers should treat 429 responses as retryable with backoff.
- DO fetch has a 30-second default timeout; set `timeoutMs` well below that to avoid double-counting active connections.

---

## Verification

```bash
# Check bulkhead status
curl 'https://my-worker.example.com/bulkhead/status?key=<redacted-secret>

# Simulate concurrency burst (requires wrk or hey)
hey -n 200 -c 50 -m POST \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u1","amountCents":100}' \
  https://my-worker.example.com/charge

# Tail logs to see 429 vs 200 distribution
wrangler tail my-worker --format pretty | grep -E '(429|granted|released)'
```

---

## Related

- `saga-pattern-workers-durable-objects.md`
- `retry-with-jitter-pattern-workers.md`
- `strangler-fig-pattern-workers-migration.md`

---

## Sources

- Cloudflare Durable Objects single-thread model — https://developers.cloudflare.com/durable-objects/best-practices/create-durable-object-stubs-and-send-requests/
- Release It! — Bulkhead pattern — https://pragprog.com/titles/mnee2/release-it-second-edition/
- Microsoft Azure — Bulkhead pattern — https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead
