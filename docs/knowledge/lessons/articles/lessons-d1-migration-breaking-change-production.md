# D1 Migration Breaking Change in Production — DROP COLUMN on Live Traffic

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After running a D1 migration that executed `ALTER TABLE orders DROP COLUMN legacy_notes`, the deployed Worker began returning HTTP 500 for every request that read from the `orders` table. The migration succeeded with exit code 0 and the column was gone, but the Worker code still contained `SELECT legacy_notes FROM orders`. Traffic was broken for 14 minutes until a hotfix Worker was deployed.

---

## Context

D1 is Cloudflare's serverless SQLite-compatible database. Migrations are applied via `wrangler d1 migrations apply` and take effect immediately on the live database. Unlike traditional deployments where a database change and a code change can be coordinated in a single atomic rollout, Cloudflare Workers and D1 are independently versioned: the database mutation is instant, but the Worker build-and-deploy pipeline takes 1–3 minutes. This creates a window where the new schema and the old Worker code are simultaneously live. `ALTER TABLE ... DROP COLUMN` removes the column immediately, and any in-flight Worker code that references the column by name will receive a SQLite error.

---

## Root Cause

The team applied a destructive schema change before deploying the compatible Worker code. The expand-contract (parallel change) pattern was not followed.

```typescript
// worker/src/orders.ts — OLD Worker referencing the dropped column
import type { D1Database } from '@cloudflare/workers-types';

export async function getOrder(db: D1Database, orderId: string) {
  // BAD: legacy_notes was dropped in the migration that just ran
  const row = await db
    .prepare('SELECT id, total, legacy_notes FROM orders WHERE id = ?')
    .bind(orderId)
    .first();
  return row;
}
```

```sql
-- migrations/0012_drop_legacy_notes.sql  ← applied BEFORE new Worker deployed
ALTER TABLE orders DROP COLUMN legacy_notes;
```

SQLite returns `table orders has no column named legacy_notes`, which D1 surfaces as an unhandled exception, causing a 500.

---

## Fix

The fix is the **expand-contract** migration pattern, also called parallel-change. A destructive schema change is split across (at minimum) two separate deployments separated by a complete Worker rollout.

### Phase 1 — Expand (add new, keep old)

```sql
-- migrations/0012_add_notes.sql
ALTER TABLE orders ADD COLUMN notes TEXT;
```

```typescript
// worker/src/orders.ts — Phase 1 Worker: reads both, writes only new column
export async function getOrder(db: D1Database, orderId: string) {
  const row = await db
    .prepare('SELECT id, total, notes, legacy_notes FROM orders WHERE id = ?')
    .bind(orderId)
    .first<{ id: string; total: number; notes: string | null; legacy_notes: string | null }>();

  return {
    ...row,
    // Coalesce: use new column if populated, fall back to legacy
    notes: row?.notes ?? row?.legacy_notes ?? null,
  };
}

export async function updateOrderNotes(
  db: D1Database,
  orderId: string,
  text: string,
) {
  // Write ONLY to the new column going forward
  await db
    .prepare('UPDATE orders SET notes = ? WHERE id = ?')
    .bind(text, orderId)
    .run();
}
```

**Deploy Phase 1 Worker and verify it is serving 100% of traffic before proceeding.**

### Phase 2 — Contract (drop old column)

Once all Workers reference only `notes`, the old column can be safely removed.

```sql
-- migrations/0013_drop_legacy_notes.sql  (applied AFTER Phase 1 Worker is deployed)
ALTER TABLE orders DROP COLUMN legacy_notes;
```

```typescript
// worker/src/orders.ts — Phase 2 Worker: references only the new column
export async function getOrder(db: D1Database, orderId: string) {
  return db
    .prepare('SELECT id, total, notes FROM orders WHERE id = ?')
    .bind(orderId)
    .first();
}
```

---

## Prevention / Detection

```typescript
// scripts/check-column-refs.ts — CI guard
// Parses migration files about to be applied and rejects destructive DDL
// unless the migration is tagged as safe-to-apply.
import { readFileSync, readdirSync } from 'fs';

const DANGEROUS_DDL = /ALTER\s+TABLE\s+\w+\s+DROP\s+COLUMN/i;

function checkMigrations(dir: string): void {
  const files = readdirSync(dir).filter(f => f.endsWith('.sql'));
  for (const file of files) {
    const sql = readFileSync(`${dir}/${file}`, 'utf8');
    if (DANGEROUS_DDL.test(sql)) {
      const hasSafeTag = sql.includes('-- safe-to-apply: expand-contract-phase-2');
      if (!hasSafeTag) {
        console.error(
          `[CI] ${file} contains DROP COLUMN without expand-contract tag. ` +
          'Add the tag only after the Phase 1 Worker is deployed.',
        );
        process.exit(1);
      }
    }
  }
  console.log('Migration safety check passed.');
}

checkMigrations('./migrations');
```

```bash
# Run in CI before wrangler d1 migrations apply
node --loader ts-node/esm scripts/check-column-refs.ts
```

---

## Anti-patterns

- **Deploying migrations and Worker code in a single step** — the migration takes effect before the Worker build completes; there will always be a window of incompatibility.
- **Using `SELECT *` to avoid naming columns** — avoids the immediate 500 but causes silent data loss when a column disappears; always name columns explicitly.
- **Skipping the expand phase for "small" changes** — column removal is always destructive; the size of the column does not matter.

---

## Gotchas

- D1 migrations run against the live production database. There is no dry-run mode that touches real data. Test against a staging D1 instance first: `wrangler d1 migrations apply DB --env staging`.
- `wrangler d1 migrations apply` applies *all* pending migrations in sequence. If migrations 0012 and 0013 are both pending, they will both run in one command — make sure 0013 (the drop) is never pending at the same time as an un-deployed Phase 1 Worker.
- D1 does not yet support transactional DDL; a failed migration mid-sequence can leave the schema in a partially applied state.

---

## Verification

```bash
# 1. Apply Phase 1 migration (add column)
wrangler d1 migrations apply DB --env production

# 2. Deploy Phase 1 Worker
wrangler deploy --env production

# 3. Smoke-test: confirm both columns are readable and 0 errors in tail
wrangler tail --env production --format=json | jq 'select(.outcome=="exception")'

# 4. After 24h with no errors, apply Phase 2 migration (drop column)
# First, tag the migration file:
# echo '-- safe-to-apply: expand-contract-phase-2' >> migrations/0013_drop_legacy_notes.sql
wrangler d1 migrations apply DB --env production

# 5. Deploy Phase 2 Worker
wrangler deploy --env production
```

---

## Related

- `lessons-kv-metadata-size-exceeded.md`

---

## Sources

- Cloudflare D1 Migrations — https://developers.cloudflare.com/d1/reference/migrations/
- Parallel Change (Expand-Contract) Pattern — https://martinfowler.com/bliki/ParallelChange.html
- SQLite ALTER TABLE — https://www.sqlite.org/lang_altertable.html
