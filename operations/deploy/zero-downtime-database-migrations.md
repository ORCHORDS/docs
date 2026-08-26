# Zero-Downtime Database Migrations

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A migration that renames or drops a column causes 500
errors during the deploy window because old Worker code
reads the column that the new migration already removed,
or new Worker code references a column that does not yet
exist in the schema.

## Context

Workers and Pages Functions are deployed as atomic units,
but the database they connect to is shared and mutable.
There is always a window — however brief — where old code
and new code run concurrently against the same D1 schema.
Migrations that change column names, drop columns, or
change NOT NULL constraints in a single step break that
overlap window. The expand-contract pattern eliminates the
risk by splitting every destructive schema change into
at least two backward-compatible deploys.

## The Expand-Contract Pattern

Each destructive change becomes a three-phase sequence:

| Phase    | Schema action          | Code action                   |
|----------|------------------------|-------------------------------|
| Expand   | ADD COLUMN new_col     | Write both old and new column |
| Migrate  | Backfill new_col data  | Read from new_col             |
| Contract | DROP COLUMN old_col    | Remove references to old_col  |

Example — renaming `user_name` to `display_name`:

**Phase 1 — Expand (deploy together with dual-write code)**
```sql
-- migrations/0012_add_display_name.sql
ALTER TABLE users ADD COLUMN display_name TEXT;
UPDATE users SET display_name = user_name;
```

**Phase 2 — Read from new column (separate deploy)**
```typescript
// All reads now use display_name; writes go to both
const name = row.display_name ?? row.user_name;
```

**Phase 3 — Contract (after phase 2 is stable in prod)**
```sql
-- migrations/0013_drop_user_name.sql
ALTER TABLE users DROP COLUMN user_name;
```

Never combine phases 1 and 3 into a single migration.

## D1 Migration Execution: Workers vs CI

Two strategies for running D1 migrations:

**Option A — CI/CD pipeline (recommended)**
```yaml
# .github/workflows/deploy.yml
- name: Apply D1 migrations
  run: |
    wrangler d1 migrations apply myapp-db \
      --env production
- name: Deploy Worker
  run: wrangler deploy --env production
```

Migrations run before the new Worker code goes live.
The old Worker code must tolerate the expanded schema
(i.e. the new column exists but the old one is still
present). This is always true if you follow expand-contract.

**Option B — Worker startup (use with caution)**
```typescript
// index.ts
export default {
  async fetch(request: Request, env: Env) {
    await runPendingMigrations(env.DB);   // idempotent
    return router.handle(request, env);
  },
};
```

Option B creates a thundering-herd risk: every instance
that starts during a cold-start wave runs the migration
concurrently. Use D1's advisory lock or a dedicated
migration Worker invoked once from CI instead.

## Blue-Green Deploy with a Shared Database

When running blue-green at the Worker layer with a single
D1 database, the expand-contract invariant becomes a hard
requirement because both the blue and green Worker versions
query the same database simultaneously during the traffic-
split window:

```
                    ┌──────────────┐
Traffic ──── 50% ──▶│ Worker v1.2  │──┐
             50% ──▶│ Worker v1.3  │──┼──▶ D1 (shared)
                    └──────────────┘  │
                                      │  Schema must satisfy
                                      │  BOTH versions
```

Schema compatibility checklist before any blue-green cut:
- New columns have DEFAULT or are nullable
- No column renamed or dropped in this migration
- No constraint tightened (e.g. NOT NULL added) in place
- Index additions are non-blocking (D1 uses SQLite ONLINE)

## Testing Migrations Against the Production Schema

Never run migration tests only against a blank database.
Clone the production schema to a shadow D1 database and
run the pending migration against it in CI:

```bash
# Export production schema (no data)
wrangler d1 export myapp-db \
  --env production --no-data \
  --output prod-schema.sql

# Apply to shadow database in CI
wrangler d1 execute myapp-shadow \
  --file prod-schema.sql
wrangler d1 migrations apply myapp-shadow

# Run integration tests against shadow
DB_ID=$(wrangler d1 list --json \
  | jq -r '.[] | select(.name=="myapp-shadow") | .uuid')
SHADOW_DB=$DB_ID npx vitest run tests/db/
```

Add this job as a required PR check so no migration
merges without passing against the real production shape.

## Anti-patterns

- Single-step rename: `ALTER TABLE … RENAME COLUMN` while
  the old Worker version is still receiving traffic.
- Running `DROP TABLE` or `DROP COLUMN` in the same deploy
  as the code that removes the reference.
- Relying on Worker startup to sequence migrations across
  horizontally scaled instances — not safe without locking.
- Testing migrations only against the seed schema in the
  repo; production often has extra indexes or filled
  columns that expose constraint errors.

## Gotchas

- D1 does not support `ALTER TABLE … RENAME COLUMN` in
  SQLite compat mode below 3.25.0. Use ADD + UPDATE +
  DROP across two deploys instead.
- D1 migration numbering is lexicographic. Pad numbers:
  `0001_` not `1_` or files sort incorrectly after 9.
- `wrangler d1 migrations apply` is idempotent per file
  name via the `d1_migrations` tracking table. Renaming
  a migration file causes it to rerun.
- Schema exports via `wrangler d1 export` do not include
  the shadow `d1_migrations` table; recreate it manually
  if you replay migration history on the shadow DB.

## Verification

```bash
# Confirm migration applied and tracking row exists
wrangler d1 execute myapp-db --env production \
  --command "SELECT * FROM d1_migrations ORDER BY id DESC LIMIT 5;"

# Confirm old column is still present (expand phase)
wrangler d1 execute myapp-db --env production \
  --command "PRAGMA table_info(users);" \
  | grep -E "user_name|display_name"
# Both rows must appear during the overlap window
```

## Related

- `deploy/rollback-strategies-workers-pages.md`
- `deploy/blue-green-database-cutover.md`
- `database/d1-schema-design.md`
- `deploy/environment-parity-staging-production.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- https://developers.cloudflare.com/d1/best-practices/query-d1/
