# Fan-out Write to Multiple Storage Sinks from Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A single write operation must land in multiple storage systems simultaneously: the
canonical record goes to D1, an invalidated KV cache key must be deleted, an R2
object must be updated, a Queue message must be enqueued for downstream consumers,
and an Analytics Engine data point must be emitted — all triggered by one API call.
Doing these sequentially adds latency for each sink; skipping some on partial failure
leaves the system inconsistent.

## Context

Fan-out write is the write-side counterpart of scatter-gather. Where scatter-gather
reads from N sources in parallel and merges the results, fan-out write dispatches a
single mutation to N sinks in parallel. In Workers the pattern is natural: all
Cloudflare bindings (D1, KV, R2, Queues, Analytics Engine, Durable Objects) are
async, so `Promise.all()` drives them concurrently within the single-request budget
of 128 MB memory and up to 30 seconds CPU time (for Workers with no duration limit).

The critical decision is write semantics: are all sinks required (all-or-nothing),
are some optional (best-effort), or do some sinks need to be retried independently
if they fail? This article covers the common cases with explicit error handling for
each posture.

---

## Core Fan-out Dispatcher

```typescript
// src/fanout.ts
import { Env } from "./types";

export type SinkResult<T> =
  | { ok: true; sink: string; value: T }
  | { ok: false; sink: string; error: unknown };

export async function fanoutWrite<T>(
  sinks: Record<string, () => Promise<T>>
): Promise<SinkResult<T>[]> {
  const entries = Object.entries(sinks);
  const results = await Promise.allSettled(entries.map(([, fn]) => fn()));
  return results.map((result, i) => {
    const [name] = entries[i];
    if (result.status === "fulfilled") {
      return { ok: true, sink: name, value: result.value };
    }
    return { ok: false, sink: name, error: result.reason };
  });
}

export function assertAllSinksOk<T>(results: SinkResult<T>[]): void {
  const failures = results.filter((r) => !r.ok) as Extract<SinkResult<T>, { ok: false }>[];
  if (failures.length > 0) {
    const summary = failures.map((f) => `${f.sink}: ${String(f.error)}`).join("; ");
    throw new Error(`Fan-out write failed on ${failures.length} sink(s): ${summary}`);
  }
}
```

## Writing a Resource Across All Sinks

```typescript
// src/resource-service.ts
import { Env } from "./types";
import { fanoutWrite, assertAllSinksOk } from "./fanout";

export interface ResourcePayload {
  id: string;
  tenantId: string;
  name: string;
  content: string;
  metadata: Record<string, string>;
}

export async function createResource(
  payload: ResourcePayload,
  env: Env
): Promise<void> {
  const now = Date.now();
  const serialized = JSON.stringify(payload);

  const results = await fanoutWrite({
    // 1. Canonical record in D1 (required — source of truth)
    d1: async () => {
      await env.DB.prepare(
        `INSERT INTO resources (id, tenant_id, name, content, created_at)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(payload.id, payload.tenantId, payload.name, payload.content, now).run();
    },

    // 2. KV cache entry — pre-populate so the next read is a cache hit
    kv: async () => {
      await env.RESOURCE_KV.put(
        `resource:${payload.id}`,
        serialized,
        { expirationTtl: 3600 }
      );
    },

    // 3. R2 for full content (supports large payloads and CDN access)
    r2: async () => {
      await env.CONTENT_BUCKET.put(
        `tenants/${payload.tenantId}/resources/${payload.id}.json`,
        serialized,
        { httpMetadata: { contentType: "application/json" } }
      );
    },

    // 4. Queue message for downstream workers (search indexer, audit logger)
    queue: async () => {
      await env.RESOURCE_EVENTS.send({
        type: "resource.created",
        id: payload.id,
        tenantId: payload.tenantId,
        at: now,
      });
    },

    // 5. Analytics Engine data point (optional — fire-and-forget)
    analytics: async () => {
      env.ANALYTICS.writeDataPoint({
        indexes: [payload.tenantId],
        blobs: ["resource.created", payload.id],
        doubles: [serialized.length, now],
      });
    },
  });

  // D1 and Queue are required; KV, R2, Analytics are best-effort
  const critical = results.filter((r) => r.sink === "d1" || r.sink === "queue");
  assertAllSinksOk(critical);

  // Log non-critical failures without blocking the response
  for (const r of results) {
    if (!r.ok && r.sink !== "d1" && r.sink !== "queue") {
      console.error(`[fanout] Non-critical sink failed: ${r.sink}`, r.error);
    }
  }
}
```

## Fan-out Delete with Cache Invalidation

```typescript
// src/resource-service.ts (continued)

export async function deleteResource(
  resourceId: string,
  tenantId: string,
  env: Env
): Promise<void> {
  const results = await fanoutWrite({
    d1: async () => {
      const r = await env.DB.prepare(
        "DELETE FROM resources WHERE id = ? AND tenant_id = ?"
      ).bind(resourceId, tenantId).run();
      if (r.meta.changes === 0) throw new Error("Resource not found");
    },

    kv_primary: async () => {
      await env.RESOURCE_KV.delete(`resource:${resourceId}`);
    },

    kv_tenant_list: async () => {
      // Invalidate the per-tenant list cache, not just the item cache
      await env.RESOURCE_KV.delete(`tenant:${tenantId}:resource_list`);
    },

    r2: async () => {
      await env.CONTENT_BUCKET.delete(
        `tenants/${tenantId}/resources/${resourceId}.json`
      );
    },

    queue: async () => {
      await env.RESOURCE_EVENTS.send({
        type: "resource.deleted",
        id: resourceId,
        tenantId,
        at: Date.now(),
      });
    },
  });

  // D1 is the only hard requirement for a delete
  assertAllSinksOk(results.filter((r) => r.sink === "d1"));

  const failures = results.filter((r) => !r.ok && r.sink !== "d1");
  if (failures.length > 0) {
    // Schedule reconciliation via Queue — don't fail the user request
    await env.RESOURCE_EVENTS.send({
      type: "resource.reconcile_needed",
      id: resourceId,
      tenantId,
      failedSinks: failures.map((f) => f.sink),
      at: Date.now(),
    });
  }
}
```

## Worker Handler

```typescript
// src/worker.ts
import { Env } from "./types";
import { createResource, deleteResource } from "./resource-service";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/resources" && request.method === "POST") {
      const body = await request.json<{
        tenantId: string;
        name: string;
        content: string;
        metadata?: Record<string, string>;
      }>();

      const id = crypto.randomUUID();
      await createResource({ id, ...body, metadata: body.metadata ?? {} }, env);
      return Response.json({ id }, { status: 201 });
    }

    const match = url.pathname.match(/^\/api\/resources\/([^/]+)$/);
    if (match && request.method === "DELETE") {
      const resourceId = match[1];
      const tenantId = request.headers.get("X-Tenant-Id") ?? "";
      await deleteResource(resourceId, tenantId, env);
      return new Response(null, { status: 204 });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## Reconciliation Consumer

```typescript
// src/reconcile-worker.ts — handles "resource.reconcile_needed" messages
import { Env } from "./types";

interface ReconcileMessage {
  type: "resource.reconcile_needed";
  id: string;
  tenantId: string;
  failedSinks: string[];
  at: number;
}

export default {
  async queue(batch: MessageBatch<ReconcileMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { id, tenantId, failedSinks } = msg.body;
      // Re-read canonical record from D1 and replay to failed sinks
      const row = await env.DB.prepare(
        "SELECT * FROM resources WHERE id = ? AND tenant_id = ?"
      ).bind(id, tenantId).first<{ id: string; name: string; content: string }>();

      if (!row) {
        // Resource was deleted; ensure failed sinks are also cleared
        if (failedSinks.includes("kv_primary")) await env.RESOURCE_KV.delete(`resource:${id}`);
        if (failedSinks.includes("r2"))
          await env.CONTENT_BUCKET.delete(`tenants/${tenantId}/resources/${id}.json`);
        msg.ack();
        continue;
      }

      if (failedSinks.includes("kv_primary")) {
        await env.RESOURCE_KV.put(`resource:${id}`, JSON.stringify(row), { expirationTtl: 3600 });
      }
      msg.ack();
    }
  },
};
```

## Anti-patterns

- **Sequential sink writes**: adding latency for each additional sink when they are
  independent. Use `Promise.allSettled` to parallelize; total latency is max(sinks),
  not sum(sinks).
- **Treating all sinks as equally critical**: crashing the request because an
  Analytics Engine write failed (non-durable) is wrong. Classify sinks by durability
  requirement upfront.
- **Using `Promise.all` (not `Promise.allSettled`) for multi-sink writes**: one
  failed sink throws and you lose the results from sinks that succeeded.
- **No reconciliation path for partial failures**: if D1 succeeds but KV delete
  fails, the stale cache entry will serve wrong data until TTL expires. Always enqueue
  a reconcile message for non-critical sink failures on mutations.
- **Large R2 object and KV write on the hot path**: R2 puts for large objects can
  take 200–500 ms. If the object is big, move the R2 write to a Queue consumer and
  only block on D1 + KV from the request handler.

## Gotchas

- Workers have a 6 subrequest depth limit for service bindings; R2, KV, D1, and
  Queue send calls do not count against the subrequest limit.
- KV `put` is eventually consistent; the new value may not be visible immediately
  in a different colo. If you need read-your-writes, pin reads to the same colo or
  read from D1 for a short window after mutation.
- `Promise.allSettled` was available in Workers from early on but double-check your
  `compatibility_date` is >= 2021-11-02 if targeting older configs.
- Queue `send()` is at-least-once; if the Worker retries after a partial failure,
  the Queue message may be sent twice. Ensure Queue consumers are idempotent.
- D1 `run()` does not throw on 0 rows affected for UPDATE/DELETE; check
  `result.meta.changes` to detect not-found conditions before proceeding.

## Verification

```bash
# Create a resource and verify all sinks
curl -X POST https://your-worker.example.com/api/resources \
  -H "Content-Type: application/json" \
  -d '{"tenantId":"t1","name":"doc","content":"hello","metadata":{}}'

# Check D1
wrangler d1 execute example project-db --command "SELECT id FROM resources LIMIT 1"

# Check KV
wrangler kv key get --namespace-id=<id> "resource:<returned-id>"

# Check R2
wrangler r2 object get example project-content "tenants/t1/resources/<returned-id>.json"
```

## Related

- `fan-out-queues-workers.md` — queue-only fan-out to multiple consumers
- `scatter-gather-parallel-workers.md` — parallel reads (the read-side complement)
- `outbox-pattern-d1-reliable-publishing.md` — guaranteed event emission via D1
- `write-behind-cache-kv-d1.md` — deferred write from KV to D1
- `compensating-transaction-payment-flows.md` — rolling back across sinks on failure

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/
- https://developers.cloudflare.com/queues/configuration/javascript-apis/
- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/d1/worker-api/
