# Using D1 Read Replicas in Workers for Read Scaling

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker handles a high read-to-write ratio and D1 primary latency is noticeable for globally distributed users. D1's read replication feature places replica copies near each Cloudflare region, dramatically reducing SELECT latency for the majority of traffic while all writes still go to the primary.

---

## Context

D1 read replication is an opt-in feature (currently in open beta) that automatically maintains SQLite replicas across Cloudflare's network. Each Worker binding can be configured to target either the primary or the nearest replica. You configure two separate bindings in `wrangler.toml` — one for the primary (`DB`) and one for the replica (`DB_REPLICA`) — then route reads to the replica and writes to the primary in application code. The main operational concern is replication lag: after a write to the primary, the replica may be 100–500 ms behind, which can cause a user to read stale data if they immediately fetch the resource they just mutated. The read-your-writes pattern handles this by routing the follow-up read to the primary when a write occurred in the same request.

---

## Config — wrangler.toml Bindings

```toml
# wrangler.toml
name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"                      # Primary — used for all writes
database_name = "orchords-db"
database_id = "YOUR_DATABASE_ID"

[[d1_databases]]
binding = "DB_REPLICA"              # Read replica — nearest region
database_name = "orchords-db"
database_id = "YOUR_DATABASE_ID"
read_replication = { mode = "closest" }   # 'closest' | 'primary'
migrations_table = "d1_migrations"        # Must match primary
```

---

## Implementation

```typescript
// src/lib/db-router.ts

/**
 * A lightweight DB router that tracks whether a write has occurred in the
 * current request. After a write, reads are redirected to the primary to
 * implement read-your-writes consistency.
 */
export class DbRouter {
  private wroteInThisRequest = false;

  constructor(
    private readonly primary: D1Database,
    private readonly replica: D1Database
  ) {}

  /** Use for all SELECT statements. Automatically falls back to primary
   *  if a write occurred earlier in this request. */
  get read(): D1Database {
    return this.wroteInThisRequest ? this.primary : this.replica;
  }

  /** Always the primary; also marks that a write occurred. */
  get write(): D1Database {
    this.wroteInThisRequest = true;
    return this.primary;
  }

  /** Explicitly mark a write occurred (e.g. after a batch write). */
  markWrite(): void {
    this.wroteInThisRequest = true;
  }
}
```

```typescript
// src/routes/posts.ts
import { Hono } from 'hono';
import { DbRouter } from '../lib/db-router';

type Env = {
  Bindings: {
    DB: D1Database;         // primary
    DB_REPLICA: D1Database; // nearest replica
  };
};

const app = new Hono<Env>();

// Attach a per-request DbRouter to every request.
app.use('*', async (c, next) => {
  c.set('dbRouter', new DbRouter(c.env.DB, c.env.DB_REPLICA));
  await next();
});

declare module 'hono' {
  interface ContextVariableMap {
    dbRouter: DbRouter;
  }
}

app.get('/posts/:id', async (c) => {
  const router = c.get('dbRouter');
  const { results } = await router.read
    .prepare(`SELECT * FROM posts WHERE id = ?`)
    .bind(c.req.param('id'))
    .all();

  if (!results[0]) return c.json({ error: 'not found' }, 404);
  return c.json(results[0]);
});

app.post('/posts', async (c) => {
  const router = c.get('dbRouter');
  const body = await c.req.json<{ title: string; body: string; author_id: string }>();
  const now = new Date().toISOString();

  // Write to primary.
  const { results } = await router.write
    .prepare(
      `INSERT INTO posts (title, body, author_id, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?)
       RETURNING *`
    )
    .bind(body.title, body.body, body.author_id, now, now)
    .all();

  // Read-your-writes: router.read now returns primary because markWrite was
  // called inside DbRouter.write getter.
  const post = results[0];
  return c.json(post, 201);
});

/**
 * Graceful fallback: if the replica throws, retry on primary.
 */
async function readWithFallback<T>(
  router: DbRouter,
  query: string,
  bindings: unknown[]
): Promise<T[]> {
  try {
    const stmt = router.read.prepare(query);
    const bound = bindings.reduce((s, b) => s.bind(b), stmt as any);
    const { results } = await bound.all<T>();
    return results;
  } catch (err) {
    // Replica unavailable — fall back to primary silently.
    console.warn('D1 replica error, falling back to primary:', err);
    const stmt = router.write.prepare(query);  // .write marks the write flag but
    // we still treat this as a read; reset the flag manually to avoid
    // penalising subsequent reads in the same request.
    const bound = bindings.reduce((s, b) => s.bind(b), stmt as any);
    const { results } = await bound.all<T>();
    return results;
  }
}

export default app;
```

---

## Testing / Verification

```typescript
// src/lib/db-router.test.ts
import { describe, it, expect, vi } from 'vitest';
import { DbRouter } from './db-router';

function makeDb(name: string): D1Database {
  return { _name: name, prepare: vi.fn() } as unknown as D1Database;
}

describe('DbRouter', () => {
  it('routes reads to replica by default', () => {
    const primary = makeDb('primary');
    const replica = makeDb('replica');
    const router = new DbRouter(primary, replica);
    expect(router.read).toBe(replica);
  });

  it('routes reads to primary after a write', () => {
    const primary = makeDb('primary');
    const replica = makeDb('replica');
    const router = new DbRouter(primary, replica);
    router.write; // trigger write flag
    expect(router.read).toBe(primary);
  });

  it('markWrite switches subsequent reads to primary', () => {
    const primary = makeDb('primary');
    const replica = makeDb('replica');
    const router = new DbRouter(primary, replica);
    expect(router.read).toBe(replica);
    router.markWrite();
    expect(router.read).toBe(primary);
  });

  it('write getter always returns primary', () => {
    const primary = makeDb('primary');
    const replica = makeDb('replica');
    const router = new DbRouter(primary, replica);
    expect(router.write).toBe(primary);
  });
});
```

---

## Anti-patterns

- **Running writes against the replica binding** — replica bindings are read-only; write attempts will throw a D1 error. Always verify your routing logic channels `INSERT`/`UPDATE`/`DELETE` to the primary.
- **Using a single shared `DbRouter` instance across requests** — the `wroteInThisRequest` flag must be request-scoped; a module-level singleton will bleed state between concurrent requests.
- **Ignoring replication lag for user-facing mutations** — without the read-your-writes pattern, a user who creates a post and immediately reloads may see the old list because the replica hasn't caught up.
- **Setting `read_replication = { mode = "primary" }`** — this disables the replica's purpose; only use it temporarily for debugging.

---

## Gotchas

- `migrations_table` must be set to the same value in both the primary and replica bindings, or Wrangler migration commands may conflict.
- The `closest` mode chooses the replica with the lowest network latency at request time — this is not always geographically closest.
- Cloudflare measures replication lag in p99 at roughly 100–500 ms under normal load; spikes during high-write bursts can reach a few seconds.
- D1 read replication is scoped to the database; you cannot replicate only selected tables.
- During a Cloudflare maintenance window, a replica can temporarily serve the primary, making `DB` and `DB_REPLICA` resolve to the same node.

---

## Verification

```bash
# Confirm both bindings resolve to the same database_id
wrangler d1 info orchords-db

# Measure round-trip time to replica vs primary from a specific region
wrangler dev --test-scheduled  # check Worker logs for timing

# Check D1 replication status via Cloudflare dashboard API
curl -s https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/d1/database/$DB_ID \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.read_replication'
```

---

## Related

- `d1-upsert-conflict-resolution.md`
- `d1-soft-delete-restore-pattern.md`

---

## Sources

- Cloudflare D1 Read Replication — https://developers.cloudflare.com/d1/reference/read-replication/
- Cloudflare D1 Configuration — https://developers.cloudflare.com/d1/configuration/
- Wrangler D1 Bindings — https://developers.cloudflare.com/workers/wrangler/configuration/
