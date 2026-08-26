# D1 Zero-Downtime Schema Migration Workers Compatibility

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A D1 schema migration that adds a NOT NULL column, renames a table, or drops a
column will break the currently-deployed Worker the instant the migration runs,
because the live Worker code still issues SQL that references the old schema. For
example project / example.com, a migration that adds `content_hash TEXT NOT NULL` to the
posts table will cause every anonymous post write to fail with a constraint
violation until the Worker referencing the new column is also deployed — creating
an unavoidable outage window if both changes are not carefully sequenced.

## Context

Cloudflare Workers and D1 run in separate planes: the Worker version is controlled
by `wrangler deploy` and the D1 schema is controlled by `wrangler d1 migrations
apply`. There is no atomic transaction across both. Zero-downtime migration
requires a multi-step "expand/contract" pattern where schema changes are
backward-compatible with both the old and new Worker versions simultaneously for
at least one deploy cycle. The Workers compatibility date setting is a separate
concern but must be reviewed when migrations touch runtime behavior.

## Section 1 — expand/contract migration pattern

Never make a breaking schema change in a single migration. Instead, use a
three-phase expand/contract cycle:

- **Expand:** Add new columns as nullable or with defaults; add new tables. The
  existing Worker ignores the new columns. The new Worker writes to both old and
  new columns during the transition.
- **Backfill:** Migrate existing rows to populate new columns. Run as a separate
  migration or a background Worker task.
- **Contract:** Drop old columns or add the NOT NULL constraint once all Workers
  use the new schema exclusively.

```sql
-- migrations/0005_expand_add_content_hash.sql
-- Phase 1 EXPAND: add content_hash as nullable (backward-compatible)
ALTER TABLE posts ADD COLUMN content_hash TEXT;

-- migrations/0006_backfill_content_hash.sql
-- Phase 2 BACKFILL: compute hash for existing rows
-- Run after 0005 and after the new Worker (which populates content_hash on write) is deployed
UPDATE posts
SET content_hash = lower(hex(randomblob(32)))  -- replace with actual hash logic
WHERE content_hash IS NULL;

-- migrations/0007_contract_content_hash_notnull.sql
-- Phase 3 CONTRACT: add NOT NULL constraint (safe only after backfill + old Worker retired)
-- SQLite/D1 does not support ALTER COLUMN; recreate the table
CREATE TABLE posts_new (
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER,
  flagged INTEGER DEFAULT 0
);

INSERT INTO posts_new SELECT id, content, content_hash, created_at, expires_at, flagged
FROM posts;

DROP TABLE posts;
ALTER TABLE posts_new RENAME TO posts;
```

## Section 2 — migration sequencing with wrangler

Apply migrations in sequence. Never skip a migration number. The `wrangler d1
migrations apply` command applies all unapplied migrations in order.

```bash
# scripts/apply-d1-migrations.sh
#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${D1_DB_NAME:?Must set D1_DB_NAME}"
ENV="${DEPLOY_ENV:-production}"

echo "Applying D1 migrations for ${DB_NAME} (${ENV})"

# Dry-run first: see what would be applied without touching the DB
npx wrangler d1 migrations apply "$DB_NAME" \
  --env "$ENV" \
  --remote \
  --dry-run

echo "--- Dry-run passed. Applying for real. ---"

npx wrangler d1 migrations apply "$DB_NAME" \
  --env "$ENV" \
  --remote

echo "Migrations applied successfully."
```

Configure migration directory in `wrangler.toml`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
migrations_dir = "migrations"
migrations_table = "d1_migrations"
```

## Section 3 — compatibility date and migration coordination

The Workers `compatibility_date` controls which runtime APIs and behaviors are
active. Some D1 API changes (e.g., prepared statement semantics, batch return
format) are gated behind compatibility dates. When a migration and a compatibility
date bump coincide, sequence them in separate deploys to isolate failure causes.

```typescript
// src/db/posts.ts — dual-write during expand phase
export async function createPost(
  db: D1Database,
  content: string
): Promise<void> {
  const id = crypto.randomUUID();
  const contentHash = await computeHash(content);
  const now = Math.floor(Date.now() / 1000);

  // During expand phase: write both content and content_hash
  // Old schema (before migration): content_hash column doesn't exist yet, skip
  // New schema (after expand migration): write content_hash
  await db
    .prepare(
      `INSERT INTO posts (id, content, content_hash, created_at)
       VALUES (?, ?, ?, ?)`
    )
    .bind(id, content, contentHash, now)
    .run();
}

async function computeHash(content: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(content)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
```

The Worker during the expand phase must handle both schema states. Use a try/catch
or schema introspection to detect which schema is active:

```typescript
// Detect schema state at startup or first request
let hasContentHash: boolean | null = null;

async function checkSchemaState(db: D1Database): Promise<boolean> {
  if (hasContentHash !== null) return hasContentHash;

  const result = await db
    .prepare("PRAGMA table_info(posts)")
    .all<{ name: string }>();

  hasContentHash = result.results.some((col) => col.name === "content_hash");
  return hasContentHash;
}
```

## Section 4 — rollback strategy

D1 migrations do not support automatic rollback — SQLite DDL statements are
not transactional in the same way DML is. Maintain explicit down-migration SQL
for each migration file.

```sql
-- migrations/0005_expand_add_content_hash.down.sql
-- Rollback for 0005: remove content_hash column (recreate table without it)
CREATE TABLE posts_v4 (
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER,
  flagged INTEGER DEFAULT 0
);

INSERT INTO posts_v4 SELECT id, content, created_at, expires_at, flagged FROM posts;
DROP TABLE posts;
ALTER TABLE posts_v4 RENAME TO posts;
```

```bash
# scripts/rollback-d1-migration.sh
#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${D1_DB_NAME:?}"
MIGRATION_NUMBER="${1:?Pass migration number to roll back, e.g. 0005}"
DOWN_FILE="migrations/${MIGRATION_NUMBER}_*.down.sql"

echo "Rolling back D1 migration ${MIGRATION_NUMBER}"

npx wrangler d1 execute "$DB_NAME" \
  --remote \
  --file $DOWN_FILE

# Remove the migration record so it can be re-applied later
npx wrangler d1 execute "$DB_NAME" \
  --remote \
  --command "DELETE FROM d1_migrations WHERE name LIKE '${MIGRATION_NUMBER}%';"

echo "Migration ${MIGRATION_NUMBER} rolled back."
```

Roll back the Worker to the previous version first, before rolling back the
migration — the old Worker must be live before the schema reverts.

## Anti-patterns

- Running `wrangler d1 migrations apply` and `wrangler deploy` in the same
  pipeline step without sequencing — race condition between schema and Worker
- Adding NOT NULL columns without a default or backfill phase — instant failure
  on any existing row INSERT in the old Worker
- Using `DROP COLUMN` (D1 / SQLite support is limited) or `DROP TABLE` without
  confirming zero traffic uses the old schema
- Bumping the compatibility date in the same commit as a schema migration —
  makes it impossible to isolate which change caused a regression
- Skipping the `--dry-run` step before applying to production D1

## Gotchas

- D1 is SQLite-based: `ALTER TABLE` only supports `ADD COLUMN`. Renaming or
  dropping columns requires the recreate-and-rename table pattern.
- The `d1_migrations` tracking table is created automatically by wrangler. Do
  not modify it manually.
- D1 remote operations (`--remote`) count against D1 usage quotas. Backfill
  migrations on large tables may need to be batched with `LIMIT`/`OFFSET`.
- Workers isolates may be reused across requests — the `hasContentHash` cache
  above persists within an isolate lifetime. After a migration applies, new
  isolates will detect the new schema; old isolates will continue until recycled.
- `wrangler d1 migrations apply --dry-run` does NOT execute SQL; it only shows
  which migration files would run. Test the actual SQL in a preview database.

## Verification

1. Apply migration `0005` to the preview database and confirm the column exists:
   `npx wrangler d1 execute example project-preview --remote --command "PRAGMA table_info(posts);"`
2. Deploy the new Worker that writes `content_hash` — verify posts are created
   successfully in the preview environment.
3. Apply migration `0006` (backfill) and verify all existing rows have
   `content_hash IS NOT NULL`.
4. Apply migration `0007` (contract) only after confirming no old Worker version
   is deployed anywhere.
5. Test the rollback script on the preview database to confirm it restores the
   original schema without data loss.

## Related

- `/documentation/docs/policies/deploy/d1-migration-dry-run-ci-gate.md`
- `/documentation/docs/policies/deploy/d1-schema-migration-sequencing-wrangler-remote.md`
- `/documentation/docs/policies/deploy/d1-migration-rollback-automated-detection.md`
- `/documentation/docs/policies/deploy/workers-d1-pre-deploy-migration-safety.md`
- `/documentation/docs/policies/deploy/zero-downtime-database-migrations.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://www.sqlite.org/lang_altertable.html
