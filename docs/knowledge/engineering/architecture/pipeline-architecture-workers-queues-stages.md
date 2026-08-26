# Pipeline Architecture with Cloudflare Workers and Queues: Staged Processing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a multi-step processing job — ingest raw event, validate, enrich, transform, persist — and a single Worker handler is growing into a 400-line monolith. Failures in step 4 force the whole chain to retry from step 1. You want each stage to be independently deployable, independently scalable, and independently retriable.

---

## Context

Cloudflare Queues supports multiple named queues. Each queue binds to exactly one consumer Worker. A pipeline is formed by chaining queues: Stage N publishes its output message to the input queue of Stage N+1. Failures in Stage N+1 are retried without re-running Stage N.

```
HTTP → Ingest Worker → [queue-raw]
                         → Validate Worker → [queue-valid]
                                              → Enrich Worker → [queue-enriched]
                                                                 → Persist Worker → D1
```

CPU budget per Worker invocation is 30 s (on paid tier). Each stage reclaims a fresh budget; a pipeline with five 10-second stages cannot be expressed as one handler.

---

## Stage 1 – Ingest (HTTP → Queue)

```typescript
// workers/ingest.ts
import { Env } from './types';

export interface RawEvent {
  id: string;
  source: string;
  receivedAt: string;
  payload: unknown;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    const event: RawEvent = {
      id: crypto.randomUUID(),
      source: request.headers.get('X-Source') ?? 'unknown',
      receivedAt: new Date().toISOString(),
      payload: body,
    };

    await env.QUEUE_RAW.send(event, { contentType: 'json' });

    return Response.json({ id: event.id, status: 'queued' }, { status: 202 });
  },
};
```

---

## Stage 2 – Validate Worker

```typescript
// workers/validate.ts
import { Env } from './types';
import type { RawEvent } from './ingest';

interface ValidEvent extends RawEvent {
  validatedAt: string;
}

function validate(event: RawEvent): string[] {
  const errors: string[] = [];
  if (!event.id) errors.push('missing id');
  if (typeof event.payload !== 'object' || event.payload === null) {
    errors.push('payload must be an object');
  }
  return errors;
}

export default {
  async queue(batch: MessageBatch<RawEvent>, env: Env): Promise<void> {
    const valid: ValidEvent[] = [];
    const failed: Array<{ id: string; errors: string[] }> = [];

    for (const msg of batch.messages) {
      const errors = validate(msg.body);
      if (errors.length > 0) {
        failed.push({ id: msg.body.id, errors });
        msg.ack(); // do not retry malformed events
      } else {
        valid.push({ ...msg.body, validatedAt: new Date().toISOString() });
        msg.ack();
      }
    }

    if (valid.length > 0) {
      await env.QUEUE_VALID.sendBatch(
        valid.map(e => ({ body: e, contentType: 'json' }))
      );
    }

    if (failed.length > 0) {
      await env.QUEUE_DLQ.sendBatch(
        failed.map(f => ({ body: f, contentType: 'json' }))
      );
    }
  },
};
```

---

## Stage 3 – Enrich Worker (External Fetch)

```typescript
// workers/enrich.ts
import { Env } from './types';
import type { ValidEvent } from './validate';

interface EnrichedEvent extends ValidEvent {
  geo?: { country: string; region: string };
  enrichedAt: string;
}

async function fetchGeo(ip: string, env: Env): Promise<{ country: string; region: string } | null> {
  const cached = await env.KV_GEO.get(ip, { type: 'json' }) as { country: string; region: string } | null;
  if (cached) return cached;

  const res = await fetch(`https://ipapi.internal/json/${ip}`, {
    headers: { Authorization: `Bearer ${env.GEO_API_TOKEN}` },
  });
  if (!res.ok) return null;

  const geo = await res.json() as { country: string; region: string };
  await env.KV_GEO.put(ip, JSON.stringify(geo), { expirationTtl: 86400 });
  return geo;
}

export default {
  async queue(batch: MessageBatch<ValidEvent>, env: Env): Promise<void> {
    const enriched: EnrichedEvent[] = await Promise.all(
      batch.messages.map(async msg => {
        const ip = (msg.body.payload as Record<string, string>)['ip'] ?? '';
        const geo = ip ? await fetchGeo(ip, env) : null;
        return {
          ...msg.body,
          geo: geo ?? undefined,
          enrichedAt: new Date().toISOString(),
        };
      })
    );

    batch.ackAll();

    await env.QUEUE_ENRICHED.sendBatch(
      enriched.map(e => ({ body: e, contentType: 'json' }))
    );
  },
};
```

---

## Stage 4 – Persist Worker (D1 Write)

```typescript
// workers/persist.ts
import { Env } from './types';
import type { EnrichedEvent } from './enrich';

export default {
  async queue(batch: MessageBatch<EnrichedEvent>, env: Env): Promise<void> {
    const rows = batch.messages.map(msg => msg.body);

    const placeholders = rows.map(() => '(?, ?, ?, ?)').join(', ');
    const values = rows.flatMap(r => [
      r.id,
      r.source,
      r.receivedAt,
      JSON.stringify(r.payload),
    ]);

    await env.DB.prepare(
      `INSERT OR IGNORE INTO events (id, source, received_at, payload)
       VALUES ${placeholders}`
    ).bind(...values).run();

    batch.ackAll();
  },
};
```

---

## Wrangler Configuration (wrangler.toml)

```toml
[[queues.producers]]
binding = "QUEUE_RAW"
queue = "pipeline-raw"

[[queues.producers]]
binding = "QUEUE_VALID"
queue = "pipeline-valid"

[[queues.producers]]
binding = "QUEUE_ENRICHED"
queue = "pipeline-enriched"

[[queues.producers]]
binding = "QUEUE_DLQ"
queue = "pipeline-dlq"

[[queues.consumers]]
queue = "pipeline-raw"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 3

[[queues.consumers]]
queue = "pipeline-valid"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 5
```

---

## Anti-patterns

- **God-stage handler**: putting all logic in one `queue` handler. A panic in enrichment blocks persistence indefinitely.
- **Passing large blobs between stages**: queue messages have a 128 KB limit. Store blobs in R2 and pass the object key instead.
- **Silent `ackAll` before write**: acking the whole batch before the downstream `sendBatch` succeeds means dropped messages on partial failure. Call `ackAll` only after the next enqueue succeeds.
- **Unbounded fan-out without back-pressure**: a single enrich stage that spawns one sub-fetch per message can exceed the subrequest limit (1000/invocation).

---

## Gotchas

- `MessageBatch.ackAll()` is terminal for the batch; you cannot call `msg.ack()` on individual messages afterwards.
- Queue consumer retries honour `max_retries` per **message**, not per batch. A batch of 100 where 1 message keeps failing will be re-delivered repeatedly.
- `sendBatch` to the next queue counts against the caller's subrequest budget (50 for free tier, 1000 for paid).
- Each stage Worker has its own CPU/memory limit. Enrich stages doing heavy JSON parsing benefit from starting fresh.

---

## Verification

```bash
# Tail logs for each stage independently
wrangler tail ingest-worker
wrangler tail validate-worker
wrangler tail enrich-worker
wrangler tail persist-worker

# Inspect DLQ depth to catch validation failures
wrangler queues describe pipeline-dlq
```

```typescript
// Integration test: send a raw event and poll D1 for the persisted row
const res = await fetch('https://ingest.example.com/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-Source': 'test' },
  body: JSON.stringify({ ip: '1.2.3.4', data: 'hello' }),
});
const { id } = await res.json();

// Poll D1 (via test binding) up to 10s
for (let i = 0; i < 10; i++) {
  await new Promise(r => setTimeout(r, 1000));
  const row = await env.DB.prepare('SELECT id FROM events WHERE id = ?').bind(id).first();
  if (row) { console.log('Pipeline completed in', i + 1, 's'); break; }
}
```

---

## Related

- `async-job-queue-cloudflare-queues-do.md`
- `dead-letter-queue-architecture.md`
- `backpressure-patterns.md`
- `reactive-streams-backpressure-workers-queues.md`
- `competing-consumers-queues.md`

---

## Sources

- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Cloudflare Queues limits — https://developers.cloudflare.com/queues/platform/limits/
- Pipes and Filters (Enterprise Integration Patterns) — Hohpe & Woolf, Addison-Wesley 2003
