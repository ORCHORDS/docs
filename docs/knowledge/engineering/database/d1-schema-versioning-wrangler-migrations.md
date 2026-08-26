# D1 Schema Versioning with Wrangler Migrations

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) has multiple D1 databases (production, staging, preview branches)
and a growing team. Developers applying migrations by hand cause drift between
environments. CI pipelines deploy Workers with schema versions that do not match the
live D1 database. Mobile app releases that require new columns ship before the column
exists in production D1.

## Context

Wrangler's `d1 migrations` command manages a numbered sequence of SQL files. Wrangler
records applied migrations in a special table called `d1_migrations` inside each D1
database. This ledger is separate from the `_cf_KV` internal metadata D1 uses for its
own bookkeeping.

Core concepts:
- Migration files live in `migrations/` (configurable in `wrangler.toml`).
- Files are numbered with a zero-padded integer prefix: `0001_create_users.sql`.
- Wrangler applies only migrations whose number is higher than the last recorded one.
- Each migration file is applied in a single transaction; partial failures roll back
  that file's changes.
- There is no built-in "down" migration — rollback must be implemented as a new forward
  migration.

## Directory Layout

```
example project/
├── wrangler.toml
├── migrations/
│   ├── 0001_create_users.sql
│   ├── 0002_create_products.sql
│   ├── 0003_add_metadata_to_products.sql
│   ├── 0004_create_events.sql
│   └── 0005_add_mobile_push_token.sql
└── src/
    └── worker.ts
```

`wrangler.toml` configuration:

```toml
[[d1_databases]]
binding         = "DB"
database_name   = "example project-db"
database_id     = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
migrations_dir  = "migrations"
```

## Migration Numbering Convention

```
+------------------+------------------------------+----------------------------+
| Pattern          | Example                      | Notes                      |
+------------------+------------------------------+----------------------------+
| Sequential int   | 0001_create_users.sql        | Simple; no gaps            |
| Timestamp prefix | 20260801120000_add_col.sql   | Avoids merge conflicts     |
| Semantic         | 0001_v1_create_schema.sql    | Couples to app version     |
+------------------+------------------------------+----------------------------+
```

example project uses sequential integers. Timestamp prefixes are recommended for teams where
multiple developers create migrations simultaneously — Wrangler sorts files
lexicographically, so timestamps naturally order without coordination.

## Applying Migrations

```bash
# Dry run — shows which migrations would be applied
wrangler d1 migrations list example project-db --env production

# Apply all pending migrations to production
wrangler d1 migrations apply example project-db --env production

# Apply to local dev (uses local SQLite, does not touch production)
wrangler d1 migrations apply example project-db --local

# Apply to staging
wrangler d1 migrations apply example project-db --env staging
```

## The d1_migrations Ledger

Wrangler creates a `d1_migrations` table in each D1 database on first apply:

```sql
-- Wrangler-managed; do not modify manually
CREATE TABLE d1_migrations (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    UNIQUE NOT NULL,
  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

Inspect the ledger to compare environments:

```bash
wrangler d1 execute example project-db --env production \
  --command "SELECT name, applied_at FROM d1_migrations ORDER BY id;"

wrangler d1 execute example project-db --env staging \
  --command "SELECT name, applied_at FROM d1_migrations ORDER BY id;"
```

## Rollback Strategy

D1 has no `migrations down` command. Implement rollback as a new forward migration:

```sql
-- migrations/0006_rollback_mobile_push_token.sql
-- Rollback of 0005: remove push_token column
-- SQLite does not support DROP COLUMN before 3.35; D1 version supports it.
ALTER TABLE users DROP COLUMN mobile_push_token;
```

For high-risk changes, write a paired rollback file at the same time as the forward
migration and keep it ready to apply:

```
migrations/
├── 0005_add_mobile_push_token.sql       <-- forward
├── 0005_rollback_mobile_push_token.sql  <-- NOT applied by Wrangler (no number prefix match)
```

Apply the rollback manually when needed:

```bash
wrangler d1 execute example project-db --env production \
  --file migrations/0005_rollback_mobile_push_token.sql
# Then delete 0005_* and update d1_migrations manually or via a new 0006_rollback.sql
```

## CI Gate Pattern

Enforce schema/code synchronisation in CI before deploying the Worker:

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Wrangler
        run: npm install -g wrangler

      - name: Check for unapplied migrations (staging)
        run: |
          PENDING=$(wrangler d1 migrations list example project-db --env staging 2>&1 \
            | grep -c "Not yet applied" || true)
          if [ "$PENDING" -gt 0 ]; then
            echo "ERROR: $PENDING migration(s) not applied to staging DB."
            exit 1
          fi
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Apply migrations to production
        run: wrangler d1 migrations apply example project-db --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Deploy Worker
        run: wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

The gate fails the pipeline if staging has unapplied migrations, requiring a human
decision before production deployment.

## Mobile Field Additions

When adding a column consumed by mobile app clients, apply the migration before
deploying the app update and use safe column defaults to avoid breaking existing mobile
app versions still in the wild:

```sql
-- migrations/0007_add_mobile_thumbnail_url.sql
-- Safe: nullable with default means old INSERT queries without this column still work
ALTER TABLE products
  ADD COLUMN mobile_thumbnail_url TEXT DEFAULT NULL;
```

```
+--------------------------+------------------------------------------+
| Column property          | Mobile-safe?                             |
+--------------------------+------------------------------------------+
| NOT NULL, no default     | UNSAFE — breaks old Writers              |
| NOT NULL, WITH DEFAULT   | Safe for old Writers; must backfill Reads|
| NULLABLE (DEFAULT NULL)  | Safe for both old Writers and Readers    |
+--------------------------+------------------------------------------+
```

Backfill the new column after the mobile app version with the column has rolled out to
>95 % of users:

```sql
-- migrations/0009_backfill_mobile_thumbnail_url.sql
UPDATE products
SET    mobile_thumbnail_url = 'https://cdn.example.com/thumbs/' || id || '.webp'
WHERE  mobile_thumbnail_url IS NULL;
```

## Environment Matrix

```
+-----------+--------------+------------------+----------------------------+
| Env       | Branch       | Apply trigger    | Rollback authority         |
+-----------+--------------+------------------+----------------------------+
| local     | any          | Developer manual | Developer manual           |
| preview   | PR branches  | Wrangler Pages   | Close/reopen PR            |
| staging   | main         | CI on merge      | Rollback migration + redep |
| production| tags/releases| CI on tag push   | Rollback migration + redep |
+-----------+--------------+------------------+----------------------------+
```

## Anti-patterns

- **Editing an already-applied migration file** — Wrangler tracks by filename; editing
  the file does not re-apply it. Create a new migration instead.
- **Manually inserting into `d1_migrations`** — Wrangler owns this table. Manual edits
  can desync what Wrangler thinks is applied.
- **Using `--command` in CI instead of `--file`** — `--command` bypasses the migration
  ledger entirely; changes are applied but not recorded.
- **One giant migration file** — large migrations are harder to review, cannot be
  partially applied, and take longer to execute (D1 query time limit: 30 s).
- **NOT testing migrations on staging first** — always apply to staging before
  production. D1 staging and production are separate databases.

## Gotchas

- SQLite `ALTER TABLE` supports only `ADD COLUMN` and `RENAME` (plus `DROP COLUMN`
  since SQLite 3.35, available in D1). Changing a column's type or constraints requires
  a table rebuild (create new table, copy data, drop old, rename).
- Wrangler `migrations list` output format may vary between Wrangler versions; pin
  `wrangler` in `package.json` to avoid CI surprises.
- D1 preview branches (created via Pages integration) auto-provision a new empty D1
  database per branch. Migrations must be applied to preview databases separately if
  branch tests need real data.
- `wrangler d1 migrations apply` is idempotent — running it twice applies nothing on
  the second run.

## Verification

```bash
# 1. List all applied migrations in production
wrangler d1 execute example project-db --env production \
  --command "SELECT name, applied_at FROM d1_migrations ORDER BY id;"

# 2. List pending migrations
wrangler d1 migrations list example project-db --env production

# 3. Confirm schema matches expectation
wrangler d1 execute example project-db --env production \
  --command "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;"

# 4. Diff environments
diff \
  <(wrangler d1 execute example project-db --env staging    --command "SELECT name FROM d1_migrations ORDER BY id;" 2>/dev/null) \
  <(wrangler d1 execute example project-db --env production --command "SELECT name FROM d1_migrations ORDER BY id;" 2>/dev/null)
```

## Related

- `d1-migrations-wrangler-ci-cd.md`
- `backward-compatible-migrations.md`
- `migration-rollback-strategy.md`
- `migration-linting-ci.md`
- `zero-downtime-migrations.md`

## Sources

- Wrangler D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
- D1 local development: https://developers.cloudflare.com/d1/configuration/local-development/
- SQLite ALTER TABLE: https://www.sqlite.org/lang_altertable.html
- D1 limits: https://developers.cloudflare.com/d1/platform/limits/
