# Durable Objects CRDT Distributed Counter

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a globally accurate, conflict-free counter — page views, likes, inventory decrements — that many Workers can increment simultaneously without losing updates. A plain KV write-and-read loop loses increments under concurrent load. A single Durable Object serializes writes but creates a hot spot if it lives in one region. You want a CRDT (Conflict-free Replicated Data Type) pattern that distributes write load across multiple DOs while keeping reads fast.

## Context

A grow-only counter (G-Counter) is the simplest CRDT. Each replica maintains its own shard total; global total = sum of all shard totals. Shards are Durable Objects. Workers hash the requesting client or user ID to a shard, so writes are distributed. Reads aggregate across shards. Because increments are monotonic and never conflict, merging is always safe.

For up/down counters (PN-Counter), maintain a separate G-Counter for positive and negative increments and subtract at read time.

---

## 1. Wrangler Configuration

```toml
# wrangler.toml
name = "crdt-counter"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[durable_objects.bindings]]
name = "COUNTER_SHARD"
class_name = "CounterShard"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["CounterShard"]
```

---

## 2. CounterShard Durable Object

```typescript
// src/counter-shard.ts
import { DurableObject } from "cloudflare:workers";

export class CounterShard extends DurableObject {
  private sql: SqlStorage;

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    this.sql = state.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS counter (
        key   TEXT PRIMARY KEY,
        value INTEGER NOT NULL DEFAULT 0
      )
    `);
  }

  async increment(key: string, delta = 1): Promise<number> {
    this.sql.exec(
      `INSERT INTO counter (key, value) VALUES (?, ?)
       ON CONFLICT(key) DO UPDATE SET value = value + excluded.value`,
      key,
      delta
    );
    const row = this.sql
      .exec<{ value: number }>("SELECT value FROM counter WHERE key = ?", key)
      .one();
    return row.value;
  }

  async get(key: string): Promise<number> {
    const row = this.sql
      .exec<{ value: number }>(
        "SELECT COALESCE(value, 0) AS value FROM counter WHERE key = ?",
        key
      )
      .toArray()[0];
    return row?.value ?? 0;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get("key") ?? "default";

    if (request.method === "POST") {
      const delta = parseInt(url.searchParams.get("delta") ?? "1");
      const value = await this.increment(key, delta);
      return Response.json({ shardValue: value });
    }

    const value = await this.get(key);
    return Response.json({ shardValue: value });
  }
}
```

---

## 3. Worker: Sharding and Aggregation

```typescript
// src/index.ts
const SHARD_COUNT = 8;

export interface Env {
  COUNTER_SHARD: DurableObjectNamespace;
}

function shardId(key: string, clientId: string): string {
  // Stable shard assignment per (key, client) pair
  let h = 0;
  for (const c of `${key}:${clientId}`) h = (Math.imul(31, h) + c.charCodeAt(0)) | 0;
  return `${key}:shard:${Math.abs(h) % SHARD_COUNT}`;
}

async function increment(
  env: Env,
  key: string,
  clientId: string,
  delta = 1
): Promise<void> {
  const id = env.COUNTER_SHARD.idFromName(shardId(key, clientId));
  const stub = env.COUNTER_SHARD.get(id);
  await stub.fetch(
    `https://do/shard?key=<redacted-secret>&delta=${delta}`,
    { method: "POST" }
  );
}

async function readTotal(env: Env, key: string): Promise<number> {
  // Fan-out read across all shards, sum totals
  const shards = Array.from({ length: SHARD_COUNT }, (_, i) => {
    const shardKey = `${key}:shard:${i}`;
    const id = env.COUNTER_SHARD.idFromName(shardKey);
    return env.COUNTER_SHARD.get(id).fetch(
      `https://do/shard?key=<redacted-secret>
    );
  });

  const responses = await Promise.all(shards);
  const totals = await Promise.all(
    responses.map((r) => r.json<{ shardValue: number }>())
  );
  return totals.reduce((sum, { shardValue }) => sum + shardValue, 0);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get("key") ?? "pageviews";
    const clientId = request.headers.get("CF-Connecting-IP") ?? "anon";

    if (request.method === "POST") {
      await increment(env, key, clientId);
      return Response.json({ ok: true });
    }

    const total = await readTotal(env, key);
    return Response.json({ key, total });
  },
} satisfies ExportedHandler<Env>;
```

---

## 4. PN-Counter (Increment and Decrement)

Extend `CounterShard` to track positive and negative deltas separately:

```typescript
// In CounterShard:
async incrementPN(key: string, delta: number): Promise<void> {
  const col = delta >= 0 ? "pos" : "neg";
  const abs = Math.abs(delta);
  this.sql.exec(
    `INSERT INTO counter_pn (key, pos, neg) VALUES (?, 0, 0)
     ON CONFLICT(key) DO UPDATE SET ${col} = ${col} + ?`,
    key,
    abs
  );
}

async getPN(key: string): Promise<number> {
  const row = this.sql
    .exec<{ pos: number; neg: number }>(
      "SELECT COALESCE(pos,0) AS pos, COALESCE(neg,0) AS neg FROM counter_pn WHERE key = ?",
      key
    )
    .toArray()[0];
  return row ? row.pos - row.neg : 0;
}
```

Aggregate across shards by summing `pos` totals and `neg` totals separately before subtracting — not by summing net values, which gives the same result mathematically but is clearer about the CRDT semantics.

---

## 5. Caching Reads with KV

Fan-out reads across 8 DOs add latency (~10–30 ms). Cache the aggregated total in KV with a short TTL:

```typescript
async function readTotalCached(
  env: Env & { COUNTER_CACHE: KVNamespace },
  key: string,
  ttl = 5
): Promise<number> {
  const cacheKey = `counter:total:${key}`;
  const cached = await env.COUNTER_CACHE.get(cacheKey);
  if (cached !== null) return parseInt(cached);

  const total = await readTotal(env, key);
  await env.COUNTER_CACHE.put(cacheKey, String(total), {
    expirationTtl: ttl,
  });
  return total;
}
```

Writes still go directly to shards; only reads are cached. The cache gives stale-by-at-most-TTL reads, which is acceptable for display counters.

---

## Anti-patterns

- **Single DO for all counters** — creates a write bottleneck at ~100–200 req/s for a single DO WebSocket session or storage call. Shard by counter key and client.
- **Read-modify-write in JS** — `const v = await state.storage.get("n"); await state.storage.put("n", v + 1)` is two round-trips and not atomic under concurrent requests. Use SQLite `UPDATE ... SET value = value + 1` for atomic increments.
- **Global shard enumeration from names** — DO names are not enumerable via the API. Track active shard names in a DO or KV list if you need dynamic shard counts.
- **Floating-point deltas** — SQLite `INTEGER` avoids precision loss. Store monetary amounts as integer cents, not floats.

---

## Gotchas

- `Promise.all` on 8 shard reads creates 8 DO activations per read request. If reads are frequent, the KV cache layer (section 5) is essential.
- Shards created by `idFromName` are lazy — a shard DO is not instantiated until first fetch. On very first deploy, all shard reads return 0 without error.
- `new_sqlite_classes` migration is required for SQLite storage. If you forget it, `state.storage.sql` is undefined at runtime.
- DO jurisdictions (`locationHint`) affect where a shard lives. If you set `locationHint` to `"eeur"`, all writes to that shard route to EU East regardless of requester location — useful for GDPR but raises latency for global users.

---

## Verification

```bash
# Deploy
wrangler deploy

# Send 50 concurrent increments
for i in $(seq 1 50); do
  curl -s -X POST "https://crdt-counter.<subdomain>.workers.dev?key=test" &
done
wait

# Read total — should be 50
curl "https://crdt-counter.<subdomain>.workers.dev?key=test"
# Expected: {"key":"test","total":50}
```

---

## Related

- `durable-objects-rate-limiter-pattern.md`
- `durable-objects-distributed-lock-leader-election.md`
- `durable-objects-sqlite-storage.md`
- `kv-eventually-consistent.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/storage-api/#sql-api
- https://en.wikipedia.org/wiki/Conflict-free_replicated_data_type
- https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-from-a-worker/
