# D1 Serialized Writes via Durable Objects

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
Multiple Worker invocations race to increment a counter or claim a slot in D1, producing
lost-update anomalies that neither SQLite transactions nor D1 batch APIs can prevent across
concurrent requests hitting different isolates.

## Context
D1 uses SQLite under the hood and serializes writes *within* a single Worker request, but
concurrent Worker invocations execute in separate V8 isolates with no shared memory. When
two requests both read a value, increment it, and write it back, both writes succeed and one
increment is silently discarded. Durable Objects (DO) have a single-threaded JavaScript
execution model with an actor-per-key guarantee: routing all mutating requests through one DO
instance converts fan-in concurrency into a serial queue at zero extra infrastructure cost.

## Schema Setup

```sql
-- migrations/0001_counters.sql
CREATE TABLE IF NOT EXISTS counters (
  name       TEXT    PRIMARY KEY,
  value      INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS counter_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  delta      INTEGER NOT NULL,
  actor_id   TEXT    NOT NULL,
  ts         INTEGER NOT NULL DEFAULT (unixepoch())
);
```

## Durable Object Implementation

```typescript
// src/counter-do.ts
import { DurableObject } from 'cloudflare:workers';

interface Env {
  DB: D1Database;
}

export class CounterDO extends DurableObject<Env> {
  // DOs serialize all fetch() calls — no lock needed inside the handler.
  async fetch(request: Request): Promise<Response> {
    const { name, delta } = await request.json<{ name: string; delta: number }>();

    const result = await this.env.DB.prepare(`
      INSERT INTO counters (name, value, updated_at)
        VALUES (?1, ?2, unixepoch())
      ON CONFLICT (name) DO UPDATE
        SET value      = value + excluded.value,
            updated_at = unixepoch()
      RETURNING value
    `).bind(name, delta).first<{ value: number }>();

    await this.env.DB.prepare(`
      INSERT INTO counter_log (name, delta, actor_id)
        VALUES (?1, ?2, ?3)
    `).bind(name, delta, this.ctx.id.toString()).run();

    return Response.json({ value: result!.value });
  }
}
```

## Worker Entrypoint

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  COUNTER_DO: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/increment' && request.method === 'POST') {
      const body = await request.json<{ name: string; delta?: number }>();
      const name = body.name ?? 'default';
      const delta = body.delta ?? 1;

      // One DO instance per counter name — guaranteed serial execution.
      const id = env.COUNTER_DO.idFromName(name);
      const stub = env.COUNTER_DO.get(id);

      const res = await stub.fetch('https://do/increment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, delta }),
      });

      return res;
    }

    if (url.pathname === '/read') {
      const name = url.searchParams.get('name') ?? 'default';
      // Reads bypass the DO — D1 read replicas handle fan-out.
      const row = await env.DB.prepare(
        'SELECT value FROM counters WHERE name = ?'
      ).bind(name).first<{ value: number }>();
      return Response.json({ value: row?.value ?? 0 });
    }

    return new Response('Not found', { status: 404 });
  },
};

export { CounterDO } from './counter-do';
```

## wrangler.toml Bindings

```toml
# wrangler.toml
name = "serialized-d1-writes"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[durable_objects.bindings]]
name       = "COUNTER_DO"
class_name = "CounterDO"

[[migrations]]
tag       = "v1"
new_classes = ["CounterDO"]
```

## Extending to Leaderboards

```typescript
// src/leaderboard-do.ts
import { DurableObject } from 'cloudflare:workers';

interface Env { DB: D1Database }

export class LeaderboardDO extends DurableObject<Env> {
  async fetch(request: Request): Promise<Response> {
    const { userId, score } = await request.json<{ userId: string; score: number }>();

    // Atomic compare-and-swap inside the DO's serial queue.
    await this.env.DB.batch([
      this.env.DB.prepare(`
        INSERT INTO leaderboard (user_id, score, updated_at)
          VALUES (?1, ?2, unixepoch())
        ON CONFLICT (user_id) DO UPDATE
          SET score      = MAX(score, excluded.score),
              updated_at = excluded.updated_at
      `).bind(userId, score),
      this.env.DB.prepare(`
        INSERT INTO leaderboard_history (user_id, score)
          VALUES (?1, ?2)
      `).bind(userId, score),
    ]);

    const rank = await this.env.DB.prepare(`
      SELECT COUNT(*) + 1 AS rank
        FROM leaderboard
       WHERE score > (SELECT score FROM leaderboard WHERE user_id = ?1)
    `).bind(userId).first<{ rank: number }>();

    return Response.json({ rank: rank!.rank });
  }
}
```

## Anti-patterns
- Routing *reads* through the DO — the DO is a serial bottleneck; push reads to D1 directly or via KV cache.
- Using one DO instance for all counters of all names — each unique name should map to its own DO ID via `idFromName(name)`.
- Storing counter state *only* in DO storage — DO storage is ephemeral after eviction; D1 is the source of truth.
- Catching and silently swallowing D1 errors inside the DO — the caller will see a 200 with a stale value.
- Creating unbounded DO instances (one per user-generated string) without a retention / cleanup strategy.

## Gotchas
- DO `ctx.waitUntil()` does not extend the D1 write deadline — finish all D1 writes before returning the Response.
- Each DO instance runs in exactly one Cloudflare PoP; cross-region latency is added for requests that land far from that PoP.
- `DurableObjectNamespace.idFromName()` is deterministic — the same string always maps to the same DO, so a collision in name space leaks cross-tenant writes.
- D1 batch size is capped at 1 000 statements; splitting counter logs into separate batches is necessary at high fan-in.
- Durable Objects bill per request *and* per wall-clock duration — a DO that blocks on a slow D1 write accrues DO CPU time.

## Verification

```bash
# Deploy
npx wrangler deploy

# Seed
npx wrangler d1 execute prod-db --command \
  "INSERT OR IGNORE INTO counters (name, value) VALUES ('page_views', 0);"

# Fire 50 concurrent increments and check final value
seq 1 50 | xargs -P 50 -I{} \
  curl -s -X POST https://<worker>.workers.dev/increment \
       -H 'Content-Type: application/json' \
       -d '{"name":"page_views","delta":1}'

curl "https://<worker>.workers.dev/read?name=page_views"
# Expected: {"value":50}

# Confirm no lost updates via log
npx wrangler d1 execute prod-db \
  --command "SELECT SUM(delta) FROM counter_log WHERE name='page_views';"
```

## Related
- [d1-advisory-lock-pattern-workers.md](d1-advisory-lock-pattern-workers.md)
- [d1-batch-operations-performance.md](d1-batch-operations-performance.md)
- [d1-rate-limiting-sliding-window-workers.md](d1-rate-limiting-sliding-window-workers.md)
- [d1-upsert-conflict-resolution-workers.md](d1-upsert-conflict-resolution-workers.md)

## Sources
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/best-practices/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/durable-objects/api/base-class/
