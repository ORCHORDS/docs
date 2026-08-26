# Vectorize Scheduled Vector TTL Expiry with Cron Triggers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Vectorize has no native TTL or expiry mechanism. Vectors accumulate indefinitely: stale product embeddings, expired session context, or outdated news article vectors degrade search quality and inflate index size. You need a background maintenance job that garbage-collects expired vectors without blocking live search traffic.

## Context

Cloudflare Workers Cron Triggers fire a scheduled Worker at a configurable interval. Combined with a D1 table that tracks vector metadata (ID, expiry timestamp, tenant), you can implement a full TTL lifecycle: insert time is recorded in D1, a cron Worker queries expired rows, deletes the vectors from Vectorize in batches, then removes the D1 rows. The approach scales to millions of vectors because D1 pagination keeps each cron run under the CPU time limit.

---

## 1. D1 Schema for Vector Metadata

```sql
-- migrations/0001_vector_registry.sql
CREATE TABLE IF NOT EXISTS vector_registry (
  vector_id   TEXT PRIMARY KEY,
  namespace   TEXT NOT NULL,
  tenant_id   TEXT NOT NULL,
  expires_at  INTEGER NOT NULL,   -- Unix epoch seconds
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_vr_expires ON vector_registry (expires_at);
CREATE INDEX idx_vr_tenant  ON vector_registry (tenant_id, expires_at);
```

---

## 2. Upsert Helper — Record Expiry at Ingestion Time

```typescript
// src/lib/vector-registry.ts
export interface VectorMeta {
  vectorId: string;
  namespace: string;
  tenantId: string;
  ttlSeconds: number;
}

export async function registerVector(
  db: D1Database,
  meta: VectorMeta,
): Promise<void> {
  const expiresAt = Math.floor(Date.now() / 1000) + meta.ttlSeconds;
  await db
    .prepare(
      `INSERT INTO vector_registry (vector_id, namespace, tenant_id, expires_at)
       VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT (vector_id) DO UPDATE SET expires_at = ?4`,
    )
    .bind(meta.vectorId, meta.namespace, meta.tenantId, expiresAt)
    .run();
}
```

---

## 3. Cron Worker — Batch Delete Expired Vectors

```typescript
// src/cron/expire-vectors.ts
import type { Env } from '../types';

const BATCH_SIZE = 500; // Vectorize delete limit per call
const MAX_BATCHES_PER_RUN = 10; // guard CPU wall time

export async function expireVectors(env: Env): Promise<void> {
  const nowEpoch = Math.floor(Date.now() / 1000);
  let deleted = 0;

  for (let i = 0; i < MAX_BATCHES_PER_RUN; i++) {
    const rows = await env.DB.prepare(
      `SELECT vector_id, namespace FROM vector_registry
       WHERE expires_at <= ?1
       ORDER BY expires_at ASC
       LIMIT ?2`,
    )
      .bind(nowEpoch, BATCH_SIZE)
      .all<{ vector_id: string; namespace: string }>();

    if (!rows.results.length) break;

    // Group by namespace — each index requires a separate delete call
    const byNamespace = new Map<string, string[]>();
    for (const row of rows.results) {
      const ids = byNamespace.get(row.namespace) ?? [];
      ids.push(row.vector_id);
      byNamespace.set(row.namespace, ids);
    }

    for (const [namespace, ids] of byNamespace) {
      await env.VECTORIZE.deleteByIds(ids);
      console.log(`[expire-vectors] deleted ${ids.length} from ${namespace}`);
    }

    // Remove from registry after successful vector deletion
    const placeholders = rows.results.map((_, k) => `?${k + 1}`).join(',');
    const ids = rows.results.map((r) => r.vector_id);
    await env.DB.prepare(
      `DELETE FROM vector_registry WHERE vector_id IN (${placeholders})`,
    )
      .bind(...ids)
      .run();

    deleted += rows.results.length;
    if (rows.results.length < BATCH_SIZE) break; // no more pages
  }

  console.log(`[expire-vectors] total expired: ${deleted}`);
}
```

---

## 4. Worker Entry Point with Scheduled Handler

```typescript
// src/index.ts
import { expireVectors } from './cron/expire-vectors';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Normal fetch handler — search, upsert, etc.
    return new Response('OK');
  },

  async scheduled(
    _event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    ctx.waitUntil(expireVectors(env));
  },
};
```

`wrangler.toml` cron configuration:

```toml
[triggers]
crons = ["0 * * * *"]   # hourly; tighten to "*/15 * * * *" for short TTLs
```

---

## 5. Soft-Delete Pattern for Zero-Downtime Transitions

For indexes that cannot tolerate a momentary gap between vector delete and metadata removal, use a two-phase approach: mark rows `status = 'pending_delete'` first, then let a second cron pass confirm deletion before removing the registry row. This prevents a crash between the Vectorize call and the D1 delete from leaving orphan vectors with no tracking row.

```typescript
// Phase 1 — mark
await env.DB.prepare(
  `UPDATE vector_registry SET status = 'pending_delete'
   WHERE expires_at <= ?1 AND status = 'active' LIMIT 500`,
).bind(nowEpoch).run();

// Phase 2 (next cron tick) — delete vectors then purge rows
const pending = await env.DB.prepare(
  `SELECT vector_id FROM vector_registry WHERE status = 'pending_delete' LIMIT 500`,
).all<{ vector_id: string }>();
// ... delete from Vectorize, then DELETE from D1
```

---

## Anti-patterns

- Deleting by querying Vectorize metadata filters instead of D1 — Vectorize filter queries return approximate results; D1 is the authoritative expiry source.
- Running unbounded loops in a single cron invocation — Workers have a 30-second CPU limit; batch and cap iterations.
- Skipping D1 cleanup after Vectorize delete — orphan registry rows grow the table and slow future cron runs.
- Setting cron intervals shorter than your median batch duration — overlapping invocations double-delete and waste quota.

## Gotchas

- Vectorize `deleteByIds` is idempotent — deleting an already-absent ID does not error; safe to retry.
- D1 `LIMIT` on `DELETE` requires SQLite 3.35+ which Cloudflare's D1 runtime supports; verify with `SELECT sqlite_version()`.
- Cron triggers do not retry on failure — wrap the body in try/catch and emit a metric or log to Analytics Engine for alerting.
- A Vectorize index rebuild (`vectorize rebuild`) resets the ANN graph but does not remove soft-deleted vectors; physical delete via the API is required first.

## Verification

```bash
# Confirm scheduled handler fires
wrangler tail --format pretty | grep "expire-vectors"

# Count registry rows older than now (should trend toward 0 after cron)
wrangler d1 execute DB --command \
  "SELECT COUNT(*) FROM vector_registry WHERE expires_at < unixepoch()"

# Manual cron trigger for smoke test
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT/workers/scripts/$WORKER/schedules/trigger" \
  -H "Authorization: Bearer $CF_API_TOKEN"
```

## Related

- `vectorize-index-lifecycle-management.md`
- `vectorize-batch-upsert-incremental-sync.md`
- `vectorize-ann-index-rebuild-zero-downtime.md`
- `llm-async-patterns.md`

## Sources

- Cloudflare Vectorize API — `deleteByIds` reference
- Cloudflare Workers Cron Triggers docs
- D1 SQLite dialect changelog
