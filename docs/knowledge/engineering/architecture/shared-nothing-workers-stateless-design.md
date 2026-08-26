# Shared-Nothing Architecture in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You discover that module-scope counters or caches in your Worker occasionally return stale or cross-contaminated data when traffic spikes, because multiple isolates accumulate divergent in-memory state. You need a design that is provably stateless per request so that any isolate can serve any request without correctness risk.

---

## Context

Cloudflare Workers run in V8 isolates that are created, reused, and evicted unpredictably. A single Worker may run in hundreds of concurrent isolates across Cloudflare's edge, each with its own module-scope memory that is **not shared** with any other isolate. Writing to a module-scope variable in one isolate is invisible to every other isolate, making it an unreliable place to store anything that must be consistent. The shared-nothing principle enforces that all durable state lives in external stores — D1, KV, R2, or Durable Objects — and that handlers are idempotent so retry-safe. Durable Objects are the single exception: they offer a single-threaded, strongly-consistent compute+storage unit that can act as a coordination point, but must be reached via consistent hashing to avoid creating multiple instances for the same logical entity. Measuring correctness requires a concurrent load test that deliberately probes for cross-request state bleed.

---

## Schema / Config — wrangler.toml

```toml
name = "shared-nothing-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

# All durable state lives here — never in module scope
[[kv_namespaces]]
binding = "SESSION_KV"
id = "<kv-namespace-id>"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "<d1-database-id>"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "app-assets"

[durable_objects]
bindings = [
  { name = "COUNTER", class_name = "HitCounter" }
]

[[migrations]]
tag = "v1"
new_classes = ["HitCounter"]
```

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS requests (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  path       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requests_user ON requests (user_id);
```

---

## Implementation — stateless Worker handler

```typescript
// src/index.ts
// ✅ No module-scope mutable variables.
// All state is fetched from external stores on every request.

import { HitCounter } from "./hit-counter";

export { HitCounter };

export interface Env {
  SESSION_KV: KVNamespace;
  DB: D1Database;
  ASSETS: R2Bucket;
  COUNTER: DurableObjectNamespace;
}

/** Derive a stable DO id from the logical key using consistent hashing. */
function doIdForKey(ns: DurableObjectNamespace, key: string): DurableObjectId {
  // idFromName() hashes the string consistently across all edge locations.
  return ns.idFromName(key);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // ── Session read — always from KV, never from module scope ──────
    const sessionToken = request.headers.get("Authorization") ?? "";
    const session = sessionToken
      ? await env.SESSION_KV.get<{ userId: string }>(sessionToken, "json")
      : null;

    if (!session) {
      return new Response("Unauthorised", { status: 401 });
    }

    // ── Idempotent write — use a client-supplied request id ─────────
    const requestId = request.headers.get("X-Request-Id");
    if (!requestId) {
      return new Response("X-Request-Id header required", { status: 400 });
    }

    await env.DB.prepare(
      `INSERT OR IGNORE INTO requests (id, user_id, path, created_at)
       VALUES (?, ?, ?, ?)`
    )
      .bind(requestId, session.userId, url.pathname, Date.now())
      .run();

    // ── Hit counter via DO with consistent hashing ──────────────────
    const counterId = doIdForKey(env.COUNTER, url.pathname);
    const counterStub = env.COUNTER.get(counterId);
    const countRes = await counterStub.fetch(
      new Request("https://do/increment", { method: "POST" })
    );
    const { count } = await countRes.json<{ count: number }>();

    return Response.json({
      path: url.pathname,
      userId: session.userId,
      requestId,
      hitCount: count,
    });
  },
};
```

---

## Durable Object — single-threaded coordination point

```typescript
// src/hit-counter.ts
import { DurableObject } from "cloudflare:workers";

export class HitCounter extends DurableObject {
  // Storage is in the DO's own SQLite storage, not module scope.
  async fetch(request: Request): Promise<Response> {
    if (new URL(request.url).pathname !== "/increment") {
      return new Response("Not found", { status: 404 });
    }

    const stored = await this.ctx.storage.get<number>("count");
    const count = (stored ?? 0) + 1;
    await this.ctx.storage.put("count", count);

    return Response.json({ count });
  }

  async reset(): Promise<void> {
    await this.ctx.storage.delete("count");
  }
}
```

---

## Concurrent load test — detecting cross-request state bleed

```typescript
// tests/bleed-check.ts
// Run with: npx tsx tests/bleed-check.ts
// Each request carries a unique X-Request-Id; we verify the DB recorded
// exactly that id and no other request's data leaked into the response.

const BASE = process.env.WORKER_URL ?? "https://shared-nothing-api.example.workers.dev";
const CONCURRENCY = 50;
const TOKEN = process.env.TEST_TOKEN ?? "";

interface Result {
  requestId: string;
  responseId: string;
  ok: boolean;
}

async function singleRequest(n: number): Promise<Result> {
  const requestId = `test-${n}-${crypto.randomUUID()}`;
  const res = await fetch(`${BASE}/test-path`, {
    method: "GET",
    headers: {
      Authorization: TOKEN,
      "X-Request-Id": requestId,
    },
  });

  if (!res.ok) throw new Error(`HTTP ${res.status} for request ${n}`);

  const body = await res.json<{ requestId: string }>();
  return {
    requestId,
    responseId: body.requestId,
    ok: requestId === body.requestId, // no bleed = echoed id matches sent id
  };
}

async function run(): Promise<void> {
  console.log(`Firing ${CONCURRENCY} concurrent requests…`);

  const tasks = Array.from({ length: CONCURRENCY }, (_, i) =>
    singleRequest(i)
  );
  const results = await Promise.allSettled(tasks);

  let passed = 0;
  let failed = 0;

  for (const r of results) {
    if (r.status === "rejected") {
      console.error("FAIL (rejected):", r.reason);
      failed++;
    } else if (!r.value.ok) {
      console.error(
        `BLEED: sent ${r.value.requestId}, got back ${r.value.responseId}`
      );
      failed++;
    } else {
      passed++;
    }
  }

  console.log(`\nResults: ${passed} passed, ${failed} failed`);
  if (failed > 0) process.exit(1);
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

---

## Anti-patterns

- **Module-scope mutable cache** — `const cache: Map<string, string> = new Map()` at module level appears to work under low traffic but silently diverges under concurrency; always use KV or DO storage.
- **Reading state written earlier in the same request from a different store** — cross-store reads of data just written in the same request can observe replication lag; design handlers so they do not need to read what they just wrote.
- **Using `idFromString()` or manual shard suffixes instead of `idFromName()`** — `idFromName()` is the correct consistent-hashing API; roll-your-own sharding typically breaks locality guarantees.
- **Assuming isolate reuse means shared memory** — isolate reuse only means lower cold-start latency; module-scope state from a prior request may still be stale or zero if the isolate was evicted between requests.

---

## Gotchas

- `ctx.storage.get()` in a Durable Object is strongly consistent within that DO; reads from KV are **eventually consistent** by default — use `{ cacheTtl: 0 }` or the `{ type: 'text' }` overload only when you need fresh data.
- Durable Objects created with `idFromName()` are pinned to a single Cloudflare location; choose a key that aligns with user geography when latency matters.
- `INSERT OR IGNORE` makes writes idempotent but does not update existing rows; if you need upsert semantics use `INSERT OR REPLACE` or `ON CONFLICT DO UPDATE`.
- Module-scope `const` objects (e.g. a `Map`) persist for the lifetime of the isolate but are **not** visible to other isolates — treat them as a warm cache that can disappear at any moment, never as truth.

---

## Verification

```bash
# Deploy
wrangler deploy

# Run the bleed-check load test
export WORKER_URL=https://shared-nothing-api.example.workers.dev
export TEST_TOKEN=<your-test-session-token>
npx tsx tests/bleed-check.ts

# Confirm all 50 rows landed in D1 with distinct ids
wrangler d1 execute app-db \
  --command "SELECT COUNT(DISTINCT id) AS unique_ids FROM requests WHERE id LIKE 'test-%'"
```

---

## Related

- `pipes-filters-workers-queues-pipeline.md`
- `event-store-workers-d1-append-only.md`
- `sidecar-pattern-workers-service-binding.md`

---

## Sources

- Cloudflare Workers: Isolate model — https://developers.cloudflare.com/workers/reference/how-workers-works/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Shared-Nothing Architecture (Wikipedia) — https://en.wikipedia.org/wiki/Shared-nothing_architecture
