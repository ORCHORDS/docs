# D1: Schema Change Rollback Failure After Early Deploy

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 migration adding a `NOT NULL` column (`user_tier`) succeeded at the database level, but the Worker code referencing the new column was deployed to production before the migration ran in the production environment. The result: runtime SQL errors on every write, a failed rollback attempt (you cannot un-add a `NOT NULL` column in SQLite without recreating the table), and ~18 minutes of write downtime.

## Context

- Cloudflare Workers + D1 (SQLite-backed)
- TypeScript, Wrangler v3, GitHub Actions CI/CD
- The migration was tested in a preview environment but the CI pipeline deployed the Worker before running `wrangler d1 migrations apply --remote`
- Incident date: 2026-08-18

## Timeline

1. 09:15 UTC — Migration authored: `ALTER TABLE users ADD COLUMN user_tier TEXT NOT NULL DEFAULT 'free'`
2. 09:22 UTC — PR merged; GitHub Actions job starts
3. 09:24 UTC — `wrangler deploy` step runs and succeeds (Worker now expects `user_tier` column)
4. 09:25 UTC — Migration step runs: `wrangler d1 migrations apply prod-db --remote` — but `NOT NULL DEFAULT` in the `ALTER TABLE` is missing from the migration file actually applied (file had a typo omitting `DEFAULT 'free'`)
5. 09:26 UTC — SQLite raises `NOT NULL constraint failed: users.user_tier` on every INSERT that doesn't supply the column
6. 09:27 UTC — Alerts fire; support tickets spike
7. 09:31 UTC — Team attempts to roll back migration; discovers SQLite does not support `ALTER TABLE ... DROP COLUMN` for columns with constraints in all versions
8. 09:43 UTC — Fix applied: new migration adding `DEFAULT 'free'` to existing rows + Worker hotfix
9. 09:45 UTC — Error rate returns to zero

## Root Cause

Two compounding failures:

1. **Deploy-before-migrate ordering**: The CI pipeline ran `wrangler deploy` before `wrangler d1 migrations apply`. The Worker code reached production expecting a schema that didn't exist yet.
2. **Non-backward-compatible column**: Adding `NOT NULL` without a `DEFAULT` (or with a missing `DEFAULT` due to a typo) made every existing row and new insert from old code paths fail immediately.

SQLite's `ALTER TABLE` is intentionally limited: you cannot drop columns with constraints or modify column types without a full table rebuild. This makes rollback expensive.

```sql
-- What was intended
ALTER TABLE users ADD COLUMN user_tier TEXT NOT NULL DEFAULT 'free';

-- What was actually in the migration file (typo: no DEFAULT)
ALTER TABLE users ADD COLUMN user_tier TEXT NOT NULL;
-- ^ Every existing row now has NULL in user_tier → constraint violation on read
```

## Fix

### Immediate hotfix migration

```sql
-- migrations/0005_fix_user_tier_default.sql
-- Step 1: Allow NULL temporarily so existing rows are valid
CREATE TABLE users_new (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  created_at  INTEGER NOT NULL,
  user_tier   TEXT NOT NULL DEFAULT 'free'
);

INSERT INTO users_new (id, email, created_at, user_tier)
SELECT id, email, created_at, COALESCE(user_tier, 'free')
FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;
```

```bash
# Apply hotfix
npx wrangler d1 migrations apply prod-db --remote
```

### Corrected Worker code (backward-compatible reads)

```typescript
// Before fix — crashes if user_tier is NULL
async function getUserTier(db: D1Database, userId: string): Promise<string> {
  const row = await db
    .prepare('SELECT user_tier FROM users WHERE id = ?')
    .bind(userId)
    .first<{ user_tier: string }>();
  return row!.user_tier; // throws if NULL
}

// After fix — defensive default
async function getUserTier(db: D1Database, userId: string): Promise<string> {
  const row = await db
    .prepare('SELECT user_tier FROM users WHERE id = ?')
    .bind(userId)
    .first<{ user_tier: string | null }>();
  return row?.user_tier ?? 'free'; // safe default
}
```

## Prevention

### 1. Always migrate before deploy in CI

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Wrangler
        run: npm ci

      # MIGRATION MUST COME BEFORE DEPLOY
      - name: Apply D1 migrations
        run: npx wrangler d1 migrations apply prod-db --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Deploy Worker
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

### 2. Always use backward-compatible column additions

```typescript
// scripts/validate-migration.ts  — run in CI before applying
import * as fs from 'fs';
import * as path from 'path';
import * as glob from 'glob';

const files = glob.sync('migrations/*.sql').sort();
const latestFile = files.at(-1);
if (!latestFile) process.exit(0);

const sql = fs.readFileSync(latestFile, 'utf8');

// Flag NOT NULL columns without DEFAULT
const dangerPattern = /ADD\s+COLUMN\s+\w+\s+\w+\s+NOT\s+NULL(?!\s+DEFAULT)/i;
if (dangerPattern.test(sql)) {
  console.error(
    `[validate-migration] ${path.basename(latestFile)}: ` +
    `NOT NULL column without DEFAULT found. This is a backward-incompatible change.\n` +
    `Either add DEFAULT or make the column nullable and backfill separately.`
  );
  process.exit(1);
}

console.log('[validate-migration] OK');
```

### 3. Schema migration checklist

```markdown
# Migration Checklist (add to PR template)
- [ ] Migration is backward-compatible (new columns are nullable OR have DEFAULT)
- [ ] Migration runs BEFORE deploy in CI/CD pipeline
- [ ] Rollback strategy documented (table rebuild SQL prepared if needed)
- [ ] Migration tested in preview D1 database first
- [ ] Worker code handles NULL for any new column defensively
```

## Anti-patterns

- Running `wrangler deploy` before `wrangler d1 migrations apply` in any pipeline
- Adding `NOT NULL` columns without a `DEFAULT` value in a live migration
- Assuming SQLite supports `ALTER TABLE ... DROP COLUMN` for rollback (it is limited)
- Relying solely on preview environments to validate migration correctness
- Writing Worker code that crashes hard on missing or NULL columns introduced by migrations

## Gotchas

- D1 uses SQLite under the hood; SQLite's `ALTER TABLE` is restricted compared to PostgreSQL
- Wrangler's `d1 migrations apply` is idempotent for applied migrations, but does not auto-rollback on error
- `wrangler d1 execute --remote --file` can run ad-hoc SQL for hotfixes but requires care with table locks
- D1 does not currently support multi-statement transactions across migration files atomically
- Preview D1 databases are separate from production; a migration passing in preview does not guarantee it passes in prod if data distributions differ

## Verification

```bash
# Check migration history
npx wrangler d1 migrations list prod-db --remote

# Verify column exists and has correct default
npx wrangler d1 execute prod-db --remote \
  --command "SELECT id, user_tier FROM users LIMIT 5;"

# Confirm no NULL values remain
npx wrangler d1 execute prod-db --remote \
  --command "SELECT COUNT(*) as null_count FROM users WHERE user_tier IS NULL;"

# Run integration test against the production DB binding
npx vitest run tests/integration/d1-users.test.ts
```

## Related

- `lessons-kv-namespace-wrong-binding-silent-fail.md` — Binding misconfiguration patterns
- `lessons-durable-objects-concurrent-fetch-deadlock.md` — DO production incident patterns

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://www.sqlite.org/lang_altertable.html
- https://developers.cloudflare.com/d1/best-practices/
