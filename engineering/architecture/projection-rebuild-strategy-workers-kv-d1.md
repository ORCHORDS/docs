# Projection Rebuild Strategy — Workers, KV & D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A CQRS read model (projection) in Workers KV becomes stale or corrupt after a schema change, a bug in the projection handler, or an infrastructure incident. You need to rebuild the projection from the event log in D1 without taking the service offline or causing a thundering herd on D1.

---

## Context

In an event-sourced system the event store (D1 append-only table) is the source of truth. Read models (KV, R2, or D1 read tables) are disposable derivations. Rebuilding means:

1. Replaying every event in order through the projection function
2. Writing outputs to a *shadow* namespace/table
3. Atomically promoting the shadow to live
4. Optionally deprecating the old projection

On Cloudflare Workers this is a long-running background task — best driven by a Durable Object alarm loop or a Queues pipeline to avoid the 30-second CPU wall.

---

## Event Store Schema (D1)

```sql
-- migrations/0001_events.sql
CREATE TABLE domain_events (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,
  stream_id  TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload    TEXT NOT NULL,   -- JSON
  recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_events_stream ON domain_events(stream_id, seq);
```

---

## Rebuild Coordinator (Durable Object)

```typescript
// src/ProjectionRebuilder.ts
import type { DurableObjectState } from "@cloudflare/workers-types";

interface RebuildState {
  jobId: string;
  lastSeq: number;
  shadowNamespace: string;
  status: "running" | "promoting" | "done" | "failed";
}

export class ProjectionRebuilder {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/start" && request.method === "POST") {
      const job: RebuildState = {
        jobId: crypto.randomUUID(),
        lastSeq: 0,
        shadowNamespace: `shadow_${Date.now()}`,
        status: "running",
      };
      await this.state.storage.put("job", job);
      this.state.storage.setAlarm(Date.now() + 100); // kick off immediately
      return Response.json({ jobId: job.jobId });
    }

    if (url.pathname === "/status") {
      const job = await this.state.storage.get<RebuildState>("job");
      return Response.json(job ?? { status: "idle" });
    }

    return new Response("Not found", { status: 404 });
  }

  async alarm(): Promise<void> {
    const job = await this.state.storage.get<RebuildState>("job");
    if (!job || job.status !== "running") return;

    try {
      const done = await this.processBatch(job);
      if (done) {
        await this.promote(job);
        job.status = "done";
      } else {
        // Schedule next batch in 500 ms to avoid CPU limits
        this.state.storage.setAlarm(Date.now() + 500);
      }
      await this.state.storage.put("job", job);
    } catch (err) {
      job.status = "failed";
      await this.state.storage.put("job", job);
      throw err;
    }
  }

  private async processBatch(job: RebuildState): Promise<boolean> {
    const BATCH = 200;
    const rows = await this.env.DB.prepare(
      "SELECT seq, stream_id, event_type, payload FROM domain_events WHERE seq > ? ORDER BY seq LIMIT ?"
    )
      .bind(job.lastSeq, BATCH)
      .all<{ seq: number; stream_id: string; event_type: string; payload: string }>();

    for (const row of rows.results) {
      const event = JSON.parse(row.payload);
      const projection = buildProjection(row.stream_id, row.event_type, event);
      if (projection) {
        await this.env.SHADOW_KV.put(
          `${job.shadowNamespace}:${projection.key}`,
          JSON.stringify(projection.value)
        );
      }
      job.lastSeq = row.seq;
    }

    return rows.results.length < BATCH; // done when fewer rows than batch size
  }

  private async promote(job: RebuildState): Promise<void> {
    // List shadow keys and copy to live KV namespace
    // In practice, use a KV namespace per projection version and switch via config
    const list = await this.env.SHADOW_KV.list({ prefix: `${job.shadowNamespace}:` });
    const copies = list.keys.map(async (k) => {
      const val = await this.env.SHADOW_KV.get(k.name);
      if (val) {
        const liveKey = k.name.replace(`${job.shadowNamespace}:`, "");
        await this.env.LIVE_KV.put(liveKey, val);
      }
    });
    await Promise.all(copies);
  }
}
```

---

## Projection Function (Pure, Testable)

```typescript
// src/projections/orderProjection.ts
interface OrderSummary {
  orderId: string;
  status: string;
  total: number;
  updatedAt: string;
}

export function buildProjection(
  streamId: string,
  eventType: string,
  payload: Record<string, unknown>
): { key: string; value: OrderSummary } | null {
  if (!streamId.startsWith("order:")) return null;
  const orderId = streamId.replace("order:", "");

  switch (eventType) {
    case "OrderPlaced":
      return {
        key: `order:${orderId}`,
        value: { orderId, status: "placed", total: payload.total as number, updatedAt: payload.placedAt as string },
      };
    case "OrderShipped":
      return {
        key: `order:${orderId}`,
        value: { orderId, status: "shipped", total: payload.total as number, updatedAt: payload.shippedAt as string },
      };
    default:
      return null;
  }
}
```

---

## Triggering a Rebuild from the Worker

```typescript
// src/index.ts (admin endpoint)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/admin/rebuild-projection" && request.method === "POST") {
      const id = env.PROJECTION_REBUILDER.idFromName("orders");
      const stub = env.PROJECTION_REBUILDER.get(id);
      return stub.fetch(new Request("https://do/start", { method: "POST" }));
    }
    // ... normal request routing
    return new Response("OK");
  },
};
```

---

## Cutover Without Downtime

```typescript
// Serve from live KV; fall back to rebuilding projection if key missing
async function getOrderSummary(orderId: string, env: Env): Promise<OrderSummary | null> {
  const raw = await env.LIVE_KV.get(`order:${orderId}`);
  if (raw) return JSON.parse(raw) as OrderSummary;

  // Projection gap — serve from D1 event replay (expensive path, cache after)
  const events = await env.DB.prepare(
    "SELECT event_type, payload FROM domain_events WHERE stream_id = ? ORDER BY seq"
  )
    .bind(`order:${orderId}`)
    .all<{ event_type: string; payload: string }>();

  if (events.results.length === 0) return null;
  let summary: OrderSummary | null = null;
  for (const e of events.results) {
    const p = buildProjection(`order:${orderId}`, e.event_type, JSON.parse(e.payload));
    if (p) summary = p.value;
  }
  if (summary) await env.LIVE_KV.put(`order:${orderId}`, JSON.stringify(summary), { expirationTtl: 3600 });
  return summary;
}
```

---

## Anti-patterns

- **Rebuilding in-place**: overwriting live KV keys during rebuild causes readers to see partial projections mid-replay.
- **Unbounded D1 query**: selecting all events without a `seq >` cursor will timeout; always paginate in batches.
- **Synchronous rebuild in a Worker fetch**: the 30-second wall clock limit will terminate large rebuilds; use Durable Object alarms.
- **Skipping idempotency**: if the rebuild alarm crashes mid-batch and retries, re-processing events must produce the same KV values (projection functions must be pure).

---

## Gotchas

- **KV eventual consistency**: after promoting shadow keys to live KV, reads may still return old values for up to 60 seconds globally; use a version header or Cache-Control to signal clients.
- **Alarm reliability**: DO alarms have at-least-once delivery; store `lastSeq` in durable storage before writing each batch so a retry resumes from the right offset.
- **Namespace cleanup**: old shadow namespaces must be purged after promotion to avoid KV quota exhaustion; schedule a cleanup alarm after confirming the promotion.

---

## Verification

```bash
# 1. Seed events in Wrangler dev
wrangler d1 execute DB --local --command \
  "INSERT INTO domain_events (stream_id, event_type, payload) VALUES ('order:1','OrderPlaced','{\"total\":5000,\"placedAt\":\"2026-08-23T10:00:00Z\"}')"

# 2. Trigger rebuild
curl -X POST http://localhost:8787/admin/rebuild-projection

# 3. Poll status
curl http://localhost:8787/admin/rebuild-projection/status

# 4. Confirm live KV
wrangler kv key get --binding LIVE_KV "order:1" --local
```

---

## Related

- `read-model-projection-workers-kv-cqrs.md` — normal projection write path
- `event-sourcing-d1-append-only-store.md` — event store schema and append semantics
- `durable-object-alarm-api-scheduled-retry.md` — alarm-driven background processing
- `cqrs-cloudflare-workers-d1.md` — full CQRS stack overview

---

## Sources

- Young, G. — "Rebuilding Read Models" (CQRS documents, 2010)
- Cloudflare Durable Objects Alarms API documentation
- Cloudflare KV — consistency guarantees and namespace limits
