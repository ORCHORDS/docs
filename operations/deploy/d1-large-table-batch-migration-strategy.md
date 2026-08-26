# D1 Large-Table Batch Migration Strategy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 migration that runs `ALTER TABLE` or backfills data on a table with millions
of rows hits the 30-second Worker CPU limit (or the 10-second limit on the Free
plan) and returns `Error 1001: Query timeout`. The migration file is marked as
applied in `d1_migrations` but the data transformation never completed, leaving the
schema and data in a split state.

## Context

D1 executes each SQL statement inside a single HTTP request to Cloudflare's SQLite
layer. There is no long-running connection model. Every statement must complete
within the execution time budget of the invoking Worker (or Wrangler process). For
tables under ~100 k rows this is rarely a problem, but the example project platform
ingests high-volume event data, and several tables regularly exceed 5 M rows in
production.

The standard approach of a single migration file that transforms all rows in one
statement will always fail at scale. The solution is to split the transformation
into bounded batches driven by a primary key range, executed across multiple Worker
invocations or Wrangler script calls.

---

## Approach 1 — Schema-Only Migration + Background Backfill

Keep the migration file responsible only for DDL changes (safe, fast). Run the data
backfill separately via a one-shot Durable Object or a scheduled Worker.

```typescript
// migrations/0042_add_processed_at_column.sql
-- Safe DDL only — completes in milliseconds regardless of row count
ALTER TABLE events ADD COLUMN processed_at INTEGER;
CREATE INDEX IF NOT EXISTS idx_events_processed_at ON events (processed_at);
```

```typescript
// workers/backfill-processed-at.ts
import type { Env } from '../types';

const BATCH_SIZE = 5_000;

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const startId = parseInt(url.searchParams.get('startId') ?? '0', 10);

    const { results, meta } = await env.DB.prepare(
      `UPDATE events
          SET processed_at = created_at
        WHERE id > ?
          AND processed_at IS NULL
        LIMIT ?`
    )
      .bind(startId, BATCH_SIZE)
      .run();

    const nextId = await getMaxIdUpdated(env, startId);
    return Response.json({ rowsAffected: meta.changes, nextId });
  },
};

async function getMaxIdUpdated(env: Env, after: number): Promise<number | null> {
  const row = await env.DB.prepare(
    `SELECT MAX(id) AS maxId FROM events
      WHERE id > ? AND processed_at IS NOT NULL
      LIMIT 1`
  )
    .bind(after)
    .first<{ maxId: number | null }>();
  return row?.maxId ?? null;
}
```

## Approach 2 — Cursor-Driven Migration Worker (GitHub Actions)

Drive batches from a GitHub Actions step that loops until all rows are processed.

```yaml
# .github/workflows/d1-backfill.yml
name: D1 Backfill — processed_at

on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment (staging | production)'
        required: true
        default: staging

jobs:
  backfill:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
    steps:
      - uses: actions/checkout@v4

      - name: Install wrangler
        run: npm ci && npx wrangler --version

      - name: Run schema migration first
        run: npx wrangler d1 migrations apply example project_DB --env ${{ inputs.environment }} --remote

      - name: Batch backfill
        shell: bash
        run: |
          CURSOR=0
          TOTAL=0
          while true; do
            RESULT=$(npx wrangler d1 execute example project_DB --env ${{ inputs.environment }} --remote \
              --command "UPDATE events SET processed_at = created_at
                         WHERE id > ${CURSOR} AND processed_at IS NULL LIMIT 5000;
                         SELECT changes() AS affected, MAX(id) AS cursor FROM events
                         WHERE id > ${CURSOR} AND processed_at IS NOT NULL;" \
              --json 2>/dev/null | jq -c '.[1].results[0]')
            AFFECTED=$(echo "$RESULT" | jq -r '.affected // 0')
            CURSOR=$(echo "$RESULT" | jq -r '.cursor // 0')
            TOTAL=$((TOTAL + AFFECTED))
            echo "Batch complete: +${AFFECTED} rows, cursor=${CURSOR}, total=${TOTAL}"
            if [ "$AFFECTED" -eq 0 ]; then break; fi
            sleep 0.5   # back-pressure — avoid hammering the D1 API
          done
          echo "Backfill complete. Total rows updated: ${TOTAL}"
```

## Approach 3 — Durable Object Batch Coordinator

For production environments where the backfill must run inside the Cloudflare
network (low latency to D1), a Durable Object alarm chain is the most robust
pattern.

```typescript
// durable-objects/BackfillCoordinator.ts
import type { DurableObjectState } from '@cloudflare/workers-types';
import type { Env } from '../types';

export class BackfillCoordinator {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(req: Request): Promise<Response> {
    const { action } = (await req.json()) as { action: string };
    if (action === 'start') {
      await this.state.storage.put('cursor', 0);
      await this.state.storage.put('total', 0);
      await this.state.storage.setAlarm(Date.now() + 100);
      return Response.json({ status: 'started' });
    }
    if (action === 'status') {
      const cursor = await this.state.storage.get<number>('cursor');
      const total = await this.state.storage.get<number>('total');
      const done = await this.state.storage.get<boolean>('done');
      return Response.json({ cursor, total, done: !!done });
    }
    return new Response('unknown action', { status: 400 });
  }

  async alarm(): Promise<void> {
    const cursor = (await this.state.storage.get<number>('cursor')) ?? 0;
    const total = (await this.state.storage.get<number>('total')) ?? 0;

    const { meta } = await this.env.DB.prepare(
      `UPDATE events SET processed_at = created_at
         WHERE id > ? AND processed_at IS NULL LIMIT 5000`
    )
      .bind(cursor)
      .run();

    const newTotal = total + meta.changes;
    await this.state.storage.put('total', newTotal);

    if (meta.changes === 0) {
      await this.state.storage.put('done', true);
      console.log(`BackfillCoordinator complete. Total: ${newTotal}`);
      return;
    }

    // Advance cursor to max processed ID
    const row = await this.env.DB.prepare(
      `SELECT MAX(id) AS maxId FROM events WHERE id > ? AND processed_at IS NOT NULL`
    )
      .bind(cursor)
      .first<{ maxId: number }>();
    await this.state.storage.put('cursor', row?.maxId ?? cursor);

    // Schedule next batch in 500 ms
    await this.state.storage.setAlarm(Date.now() + 500);
  }
}
```

## Approach 4 — Idempotent Re-runnable Migration Files

When the transformation logic is simple enough to express in SQL that is safe to
re-run (idempotent), encode both the DDL and a bounded DML pass in the migration
file. Accept that a full backfill requires running `wrangler d1 migrations apply`
multiple times until convergence.

```sql
-- migrations/0043_backfill_processed_at_batch.sql
-- Idempotent: safe to run repeatedly until 0 rows changed.
-- Each wrangler invocation processes one batch.

ALTER TABLE events ADD COLUMN IF NOT EXISTS processed_at INTEGER;

UPDATE events
   SET processed_at = created_at
 WHERE processed_at IS NULL
 LIMIT 5000;
```

```bash
#!/usr/bin/env bash
# scripts/apply-until-converged.sh
ENV="${1:-staging}"
while true; do
  OUTPUT=$(npx wrangler d1 migrations apply example project_DB --env "$ENV" --remote 2>&1)
  echo "$OUTPUT"
  # If wrangler reports "No migrations to apply" the backfill batch returned 0 rows
  echo "$OUTPUT" | grep -q "No migrations to apply" && break
  sleep 1
done
```

## Anti-patterns

- **Single-statement full-table UPDATE in a migration file** — will timeout on any
  table > 200 k rows and leave the migration partially applied.
- **Using `SELECT COUNT(*)` to decide batch size at runtime** — table scans on
  large D1 tables are slow and consume the CPU budget before the actual work.
- **Relying on Wrangler `--command` for backfills in production during peak load**
  — `--command` runs over HTTPS and is subject to Cloudflare API rate limits.
- **Not creating an index on the cursor column before batching** — range scans
  without an index degrade O(n) per batch, making later batches progressively
  slower.

## Gotchas

- D1's `changes()` function returns rows affected by the *most recent statement*
  in the same connection, not the entire transaction. If you chain statements in
  `--command`, ensure the SELECT follows immediately.
- Durable Object alarms fire **at least once**: the backfill coordinator must be
  idempotent — re-processing a row already set must be a no-op (`WHERE
  processed_at IS NULL`).
- Wrangler `d1 migrations apply` marks a migration as applied before executing its
  content. If the migration times out, the `d1_migrations` table still records it
  as done. Use the re-runnable pattern (Approach 4) or skip the migration system
  entirely for backfills.
- The D1 API has a 1 MB per-request payload limit. `--command` strings that embed
  large data inline will be rejected.
- Clock skew between GitHub Actions runners and Cloudflare does not affect D1
  migrations, but `created_at` values sourced from `strftime('%s', 'now')` inside
  D1 are always UTC Unix seconds — verify timezone assumptions in downstream code.

## Verification

```bash
# Confirm zero un-backfilled rows remain
npx wrangler d1 execute example project_DB --env production --remote \
  --command "SELECT COUNT(*) AS remaining FROM events WHERE processed_at IS NULL;" \
  --json | jq '.[0].results'

# Spot-check a sample
npx wrangler d1 execute example project_DB --env production --remote \
  --command "SELECT id, created_at, processed_at FROM events ORDER BY id DESC LIMIT 5;" \
  --json | jq '.[0].results'

# Confirm index was created
npx wrangler d1 execute example project_DB --env production --remote \
  --command "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND tbl_name='events';" \
  --json | jq '.[0].results'
```

## Related

- `d1-migration-dry-run-ci-gate.md`
- `d1-zero-downtime-schema-migration-workers-compatibility.md`
- `d1-schema-migration-sequencing-wrangler-remote.md`
- `durable-objects-live-migration-deploy-strategy.md`
- `workers-version-rollback-automation-health-check.md`

## Sources

- Cloudflare D1 documentation — Migrations: https://developers.cloudflare.com/d1/reference/migrations/
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
- Durable Objects alarms API: https://developers.cloudflare.com/durable-objects/api/alarms/
- SQLite `changes()` function: https://www.sqlite.org/lang_corefunc.html#changes
