# Optimistic Locking in D1 with Row Version Numbers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Two Worker requests read the same `orders` row simultaneously and both try to update `status`. Without a concurrency guard, the second write silently overwrites the first, losing the earlier update. You need a lightweight mechanism to detect and surface concurrent modifications without resorting to `SELECT … FOR UPDATE` (which SQLite does not support).

## Context

Optimistic locking assumes conflicts are rare. Each row carries a monotonically increasing `version` integer. A Writer reads the row (capturing `version = N`), performs its business logic, then updates the row with `WHERE id = ? AND version = N`. If another Writer has already incremented `version` to `N+1`, the `WHERE` clause matches zero rows — the `changes` pragma exposes this as 0 affected rows. The Worker then returns a 409 Conflict, and the client retries after re-fetching the latest state. This pattern is fully compatible with D1's single-primary architecture and requires no advisory locks.

## Schema

```sql
CREATE TABLE IF NOT EXISTS orders (
  id          TEXT    PRIMARY KEY,
  user_id     TEXT    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'pending',
  total_cents INTEGER NOT NULL,
  version     INTEGER NOT NULL DEFAULT 0,
  updated_at  INTEGER NOT NULL
);

-- Index for fast single-row lookups
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, status);
```

## Optimistic Update Pattern in Workers

```typescript
import { Env } from './types';

type Order = {
  id: string;
  user_id: string;
  status: string;
  total_cents: number;
  version: number;
  updated_at: number;
};

async function getOrder(db: D1Database, id: string): Promise<Order | null> {
  return db
    .prepare('SELECT * FROM orders WHERE id = ?')
    .bind(id)
    .first<Order>();
}

async function updateOrderStatus(
  db: D1Database,
  id: string,
  newStatus: string,
  expectedVersion: number
): Promise<{ success: boolean; conflict: boolean }> {
  const now = Date.now();

  const result = await db
    .prepare(
      `UPDATE orders
       SET status     = ?,
           version    = version + 1,
           updated_at = ?
       WHERE id      = ?
         AND version = ?`
    )
    .bind(newStatus, now, id, expectedVersion)
    .run();

  if (!result.success) {
    return { success: false, conflict: false };
  }

  // D1 exposes rows affected via result.meta.changes
  const changed = result.meta.changes ?? 0;
  if (changed === 0) {
    // WHERE version = ? matched nothing — someone else updated first
    return { success: false, conflict: true };
  }

  return { success: true, conflict: false };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'PATCH') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { id, status, version } = await request.json<{
      id: string;
      status: string;
      version: number;
    }>();

    const outcome = await updateOrderStatus(env.DB, id, status, version);

    if (outcome.conflict) {
      // Fetch the current row so the client can refresh its state
      const current = await getOrder(env.DB, id);
      return Response.json(
        { error: 'Conflict', current },
        { status: 409 }
      );
    }

    if (!outcome.success) {
      return new Response('Internal Error', { status: 500 });
    }

    return Response.json({ ok: true });
  },
};
```

## Retry-with-Refresh Pattern for the Client

```typescript
// client.ts — browser or another Worker calling the API
async function patchOrderWithRetry(
  orderId: string,
  newStatus: string,
  maxRetries = 3
): Promise<void> {
  // 1. Fetch the current row to get the latest version
  let order = await fetch(`/orders/${orderId}`).then((r) => r.json());

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const res = await fetch('/orders', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: orderId, status: newStatus, version: order.version }),
    });

    if (res.ok) return; // success

    if (res.status === 409) {
      const body = await res.json();
      // Refresh local state from the server's current row
      order = body.current;
      // Optional: back off before retrying
      await new Promise((r) => setTimeout(r, 50 * (attempt + 1)));
      continue;
    }

    throw new Error(`Unexpected status ${res.status}`);
  }

  throw new Error('Max retries exceeded — persistent conflict');
}
```

## Detecting Stale Reads

```sql
-- During development, simulate a conflict:
-- Connection A: read row (version = 5)
-- Connection B: update the row
UPDATE orders SET status = 'shipped', version = version + 1, updated_at = unixepoch()
WHERE id = 'order-123' AND version = 5;
-- changes = 1 (success)

-- Connection A: attempt update with stale version
UPDATE orders SET status = 'cancelled', version = version + 1, updated_at = unixepoch()
WHERE id = 'order-123' AND version = 5;
-- changes = 0 (conflict detected)
SELECT changes(); -- returns 0
```

## Anti-patterns

- **Not checking `changes`** — If you only check `result.success`, a 0-row update looks identical to a successful 1-row update. Always check `result.meta.changes`.
- **Using timestamps instead of integers** — Wall-clock timestamps have millisecond resolution and can collide on fast machines; a monotonic integer version is safer.
- **Unbounded retry loops** — Retrying indefinitely under a hot conflict storm amplifies D1 write pressure. Cap retries and surface the error to the user after exhaustion.
- **Skipping the version column on INSERT** — New rows must start at `version = 0` (or any fixed baseline) to make the first update predictable.

## Gotchas

- D1 returns `result.meta.changes` (not `result.changes`); destructure carefully.
- D1 is single-writer; optimistic locking primarily guards against race conditions between concurrent Worker invocations hitting the same primary, not multi-region write conflicts.
- If you use D1 `batch()` to do multiple updates atomically, check `meta.changes` on each individual result inside the batch array.
- Do not expose raw `version` integers in public APIs if they reveal business-sensitive information (e.g., order edit frequency).

## Verification

```bash
# Insert a test row
wrangler d1 execute example project-db \
  --command "INSERT INTO orders VALUES ('o1','u1','pending',1000,0,unixepoch());"

# Simulate successful update (version matches)
wrangler d1 execute example project-db \
  --command "UPDATE orders SET status='shipped', version=version+1 WHERE id='o1' AND version=0; SELECT changes();"
# Expected: changes() = 1

# Simulate conflict (stale version)
wrangler d1 execute example project-db \
  --command "UPDATE orders SET status='cancelled', version=version+1 WHERE id='o1' AND version=0; SELECT changes();"
# Expected: changes() = 0 (version is now 1, not 0)
```

## Related

- `d1-online-schema-change-zero-downtime-workers.md`
- `d1-geospatial-bounding-box-query-workers.md`
- `d1-partial-index-conditional-expressions-workers.md`

## Sources

- Cloudflare D1 `run()` and `meta` — https://developers.cloudflare.com/d1/worker-api/d1-database/#run
- SQLite `changes()` function — https://www.sqlite.org/lang_corefunc.html#changes
- Optimistic Locking Pattern — https://martinfowler.com/eaaCatalog/optimisticOfflineLock.html
