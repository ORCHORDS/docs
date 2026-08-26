# Webhook Fanout Architecture: Durable Objects as Reliable Delivery Agents

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

You publish events (payment completed, order shipped, user signed up) and need to deliver them reliably to one or more external HTTP endpoints registered by customers. Delivery must survive the target being temporarily down, must retry with exponential back-off, must respect per-endpoint rate limits, and must guarantee at-least-once delivery even if the originating Worker crashes mid-flight. Standard stateless Workers cannot hold retry state between requests.

---

## Context

Cloudflare Durable Objects (DOs) are single-threaded, location-pinned actors with durable storage and alarm scheduling. They are the correct primitive for reliable webhook delivery because:

- **State**: Each registered webhook endpoint gets its own DO instance. The DO stores the outbox (pending deliveries) and retry metadata in its built-in key-value storage.
- **Alarms**: A DO can schedule a future alarm callback to itself via `this.ctx.storage.setAlarm()`. This replaces cron jobs or external schedulers for retry back-off.
- **Concurrency control**: A single DO processes one request at a time, eliminating race conditions between concurrent delivery attempts for the same endpoint.
- **Fan-out**: An event dispatcher Worker creates (or forwards to) one DO per registered endpoint, achieving fan-out without coordination.

This is distinct from `workers-queue-fanout-architecture.md`, which uses Cloudflare Queues for fan-out but does not provide per-endpoint DO-level state and alarm-based retry.

---

## Data Model

```typescript
// src/webhook-types.ts
export interface WebhookEndpoint {
  id: string;             // Durable Object name (stable per endpoint)
  url: string;
  secret: string;         // HMAC-SHA256 signing secret
  maxRetries: number;     // Default: 7
  timeoutMs: number;      // Per-attempt HTTP timeout (default 10 000 ms)
  createdAt: string;
}

export interface OutboxEntry {
  deliveryId: string;     // UUID, stable across retries
  eventType: string;
  payload: unknown;
  enqueuedAt: string;
  attempts: number;
  nextAttemptAt: string;  // ISO timestamp for the alarm
  lastError?: string;
  status: 'pending' | 'delivered' | 'dead';
}
```

---

## Webhook Delivery Durable Object

```typescript
// src/webhook-delivery-do.ts
import { DurableObject } from 'cloudflare:workers';

const BASE_DELAY_MS  = 1_000;   // 1 s
const MAX_DELAY_MS   = 300_000; // 5 min

export class WebhookDeliveryDO extends DurableObject {
  private endpoint!: WebhookEndpoint;

  /** Called by the dispatcher Worker to enqueue a new delivery. */
  async enqueue(endpoint: WebhookEndpoint, entry: OutboxEntry): Promise<void> {
    this.endpoint = endpoint;
    await this.ctx.storage.put<OutboxEntry>(`outbox:${entry.deliveryId}`, entry);

    // Schedule an alarm for immediate delivery if none is pending
    const existing = await this.ctx.storage.getAlarm();
    if (existing === null) {
      await this.ctx.storage.setAlarm(Date.now() + 100); // near-immediate
    }
  }

  /** Alarm fires when it is time to attempt (or retry) pending deliveries. */
  async alarm(): Promise<void> {
    const endpoint = await this.ctx.storage.get<WebhookEndpoint>('endpoint');
    if (!endpoint) return;

    const all = await this.ctx.storage.list<OutboxEntry>({ prefix: 'outbox:' });
    const pending = [...all.values()].filter(e => e.status === 'pending');

    if (pending.length === 0) return;

    // Process one entry per alarm to keep wall-clock time predictable
    const entry = pending.sort(
      (a, b) => new Date(a.nextAttemptAt).getTime() - new Date(b.nextAttemptAt).getTime()
    )[0];

    const delivered = await this.attempt(endpoint, entry);

    if (delivered) {
      entry.status = 'delivered';
      await this.ctx.storage.put<OutboxEntry>(`outbox:${entry.deliveryId}`, entry);
    } else {
      entry.attempts += 1;
      if (entry.attempts >= endpoint.maxRetries) {
        entry.status = 'dead';
        await this.ctx.storage.put<OutboxEntry>(`outbox:${entry.deliveryId}`, entry);
        // Optionally publish to a DLQ via Queue binding here
      } else {
        const delay = Math.min(BASE_DELAY_MS * 2 ** entry.attempts, MAX_DELAY_MS);
        entry.nextAttemptAt = new Date(Date.now() + delay).toISOString();
        await this.ctx.storage.put<OutboxEntry>(`outbox:${entry.deliveryId}`, entry);
        await this.ctx.storage.setAlarm(Date.now() + delay);
        return;
      }
    }

    // Check if more pending items remain and re-arm the alarm
    const remaining = [...(await this.ctx.storage.list<OutboxEntry>({ prefix: 'outbox:' })).values()]
      .filter(e => e.status === 'pending');
    if (remaining.length > 0) {
      const next = Math.min(
        ...remaining.map(e => new Date(e.nextAttemptAt).getTime())
      );
      await this.ctx.storage.setAlarm(Math.max(next, Date.now() + 100));
    }
  }

  private async attempt(
    endpoint: WebhookEndpoint,
    entry: OutboxEntry,
  ): Promise<boolean> {
    const body = JSON.stringify({
      id:        entry.deliveryId,
      eventType: entry.eventType,
      payload:   entry.payload,
      timestamp: new Date().toISOString(),
    });

    const signature = await this.sign(endpoint.secret, body);

    try {
      const resp = await Promise.race([
        fetch(endpoint.url, {
          method: 'POST',
          headers: {
            'Content-Type':       'application/json',
            'X-Webhook-Signature': `sha256=${signature}`,
            'X-Delivery-Id':       entry.deliveryId,
            'X-Attempt':           String(entry.attempts + 1),
          },
          body,
        }),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('timeout')), endpoint.timeoutMs)
        ),
      ]);

      entry.lastError = resp.ok ? undefined : `HTTP ${resp.status}`;
      return resp.ok;
    } catch (err) {
      entry.lastError = (err as Error).message;
      return false;
    }
  }

  private async sign(secret: string, body: string): Promise<string> {
    const key = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign'],
    );
    const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
    return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, '0')).join('');
  }

  /** Admin API: list the outbox for this endpoint. */
  async listOutbox(): Promise<OutboxEntry[]> {
    const all = await this.ctx.storage.list<OutboxEntry>({ prefix: 'outbox:' });
    return [...all.values()].sort(
      (a, b) => new Date(a.enqueuedAt).getTime() - new Date(b.enqueuedAt).getTime()
    );
  }
}
```

---

## Dispatcher Worker (Fan-out Entry Point)

```typescript
// src/dispatcher.ts
import type { Env } from './env';

export interface DispatchRequest {
  eventType: string;
  payload: unknown;
}

export async function dispatchEvent(
  env: Env,
  event: DispatchRequest,
): Promise<void> {
  // Load registered endpoints from D1 (or KV)
  const endpoints = await env.DB.prepare(
    `SELECT id, url, secret, max_retries, timeout_ms FROM webhook_endpoints WHERE active = 1`
  ).all<{
    id: string; url: string; secret: string;
    max_retries: number; timeout_ms: number;
  }>();

  const deliveryId = crypto.randomUUID();
  const now = new Date().toISOString();

  await Promise.all(
    (endpoints.results ?? []).map(async row => {
      const stub = env.WEBHOOK_DELIVERY.get(
        env.WEBHOOK_DELIVERY.idFromName(row.id)
      );
      const endpoint: WebhookEndpoint = {
        id:         row.id,
        url:        row.url,
        secret:     row.secret,
        maxRetries: row.max_retries,
        timeoutMs:  row.timeout_ms,
        createdAt:  now,
      };
      const entry: OutboxEntry = {
        deliveryId:    `${deliveryId}-${row.id}`,
        eventType:     event.eventType,
        payload:       event.payload,
        enqueuedAt:    now,
        attempts:      0,
        nextAttemptAt: now,
        status:        'pending',
      };
      await stub.enqueue(endpoint, entry);
    })
  );
}
```

`wrangler.toml` binding:

```toml
[[durable_objects.bindings]]
name        = "WEBHOOK_DELIVERY"
class_name  = "WebhookDeliveryDO"

[[migrations]]
tag         = "v1"
new_classes = ["WebhookDeliveryDO"]
```

---

## HMAC Signature Verification (Receiver Side)

```typescript
// Receiver verifies the signature before processing
async function verifySignature(
  secret: string,
  rawBody: string,
  sigHeader: string,   // "sha256=<hex>"
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify'],
  );
  const expected = sigHeader.replace('sha256=', '');
  const expectedBytes = new Uint8Array(
    expected.match(/.{2}/g)!.map(b => parseInt(b, 16))
  );
  return crypto.subtle.verify('HMAC', key, expectedBytes, new TextEncoder().encode(rawBody));
}
```

---

## Anti-patterns

- **One DO per event (not per endpoint)**: DO instances should be pinned to the endpoint, not to individual events. Pinning per event creates unbounded DO namespace growth and wastes alarm scheduling overhead.
- **Storing large payloads in DO storage**: DO storage has per-key size limits. Keep payloads ≤128 KB; for larger events, store the payload in R2 and put only the R2 object key in the outbox entry.
- **Blocking the alarm handler on multiple deliveries**: Process one pending entry per alarm invocation. Doing N HTTP calls in a single alarm risks hitting the 30-second wall-clock limit and causes partial-delivery ambiguity.
- **Not cleaning up delivered entries**: Delivered outbox entries accumulate and slow `storage.list()` scans. Purge entries older than your retention window (e.g. 7 days) in a scheduled Worker.
- **Infinite retries**: Always enforce a `maxRetries` cap and move dead entries to a dead-letter store. Silent infinite loops exhaust DO storage and alarm budget.
- **Not signing the payload**: Unsigned webhooks allow any party to forge events to the customer's endpoint. Always sign with HMAC-SHA256 and document the header name and scheme.

---

## Gotchas

- **Alarm coalescing**: `setAlarm()` with a time in the past fires as soon as possible, not immediately. There is a minimum granularity of ~1 second in practice; do not expect sub-second precision.
- **DO eviction and hibernation**: A DO that has no in-flight requests is evicted from memory, but its durable storage and scheduled alarm persist. The alarm wakes the DO back up, so delivery is not affected by eviction.
- **`idFromName` vs. `idFromString`**: Use `idFromName(endpointId)` consistently. Mixing `idFromName` and `idFromString` with the same logical endpoint will route to different DO instances.
- **Concurrent `enqueue` calls**: The DO serializes all incoming requests, so two events enqueued simultaneously are processed in order. However, if the dispatcher sends a burst of events, the DO queue depth can grow. For very high-throughput scenarios, consider using Cloudflare Queues to buffer before enqueuing into the DO.
- **Storage list performance**: `storage.list({ prefix: 'outbox:' })` returns all keys with that prefix in memory. Cap per-endpoint outbox depth at a reasonable number (e.g. 1,000 entries) and alert when the limit is approached.

---

## Verification

```bash
# 1. Deploy and check DO migration
wrangler deploy --dry-run

# 2. Trigger a test dispatch
curl -X POST https://myapp.workers.dev/dispatch \
  -H "Content-Type: application/json" \
  -d '{"eventType":"order.shipped","payload":{"orderId":"abc123"}}'

# 3. Query the outbox state via admin API
curl https://myapp.workers.dev/admin/webhooks/<endpoint-id>/outbox

# 4. Simulate a failing endpoint (use a URL that returns 500)
# Watch the outbox show increasing attempt count and updated nextAttemptAt

# 5. Verify HMAC signature on the receiver
# The receiver should log: signature verified: true
```

---

## Related

- `workers-queue-fanout-architecture.md` — Queues-based fan-out (simpler, lower guarantees)
- `webhook-reliability-pattern-workers-queues.md` — Queues + outbox for reliable delivery
- `at-least-once-delivery.md` — general at-least-once semantics
- `durable-object-alarm-api-scheduled-retry.md` — alarm API details
- `dead-letter-queue-architecture.md` — handling dead deliveries
- `idempotency-keys-workers-api.md` — ensuring receivers are idempotent

---

## Sources

- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- DO Alarm API — https://developers.cloudflare.com/durable-objects/api/alarms/
- DO Storage API — https://developers.cloudflare.com/durable-objects/api/storage-api/
- Webhook best practices (IETF draft) — https://www.ietf.org/archive/id/draft-ietf-httpapi-webhook-best-practices-05.txt
- GitHub webhook signature verification — https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
