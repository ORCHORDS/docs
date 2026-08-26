# d1-schema-versioning-blue-green

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

A example project schema migration (adding a NOT NULL column, renaming a column,
or changing a column type) requires deploying both the Cloudflare Worker
code and the D1 DDL change atomically. If the DDL is applied before the
Worker is fully rolled out, old Worker instances fail to insert rows
missing the new column. If the Worker is deployed first, it references
a column that does not yet exist. Either order causes a brief but
observable error window on mobile clients.

## Context

Cloudflare Workers deployments use a rolling update model: new and old
Worker versions co-exist for a short window (seconds to minutes). D1 is
a single shared database with no built-in multi-version support. This
creates a classic "two-phase" database migration problem: the schema and
the application code must be compatible with both old and new Workers
simultaneously during the rollout window.

Blue-green schema migration is a discipline, not a single tool. It
decomposes every breaking schema change into at least two safe phases
and uses feature flags to gate column visibility to mobile and desktop
clients until the migration is fully complete.

Wrangler migrations (`wrangler d1 migrations apply`) handle sequential
DDL but do not coordinate with Worker deployment timing—that
coordination is the responsibility of this pattern.

## Three-Phase Migration Model

### Phase 1: Expand (additive only)

Apply DDL that is backward-compatible with the current Worker version.
Old Worker code must be able to read and write without errors after
this phase.

```sql
-- Safe: add a nullable column. Old Workers ignore it; new Workers write it.
ALTER TABLE posts ADD COLUMN reply_count INTEGER;

-- Safe: add a new index. No impact on reads/writes.
CREATE INDEX IF NOT EXISTS idx_posts_reply_count
  ON posts (community_id, reply_count DESC, id ASC);

-- Safe: add a new table. Old Workers never touch it.
CREATE TABLE IF NOT EXISTS post_replies (
  id         TEXT    PRIMARY KEY,
  post_id    TEXT    NOT NULL REFERENCES posts(id),
  body       TEXT    NOT NULL,
  created_at INTEGER NOT NULL
);
```

Deploy the DDL migration. Wait for full propagation across all D1
replicas (typically < 30 s). Then deploy the new Worker version.

### Phase 2: Migrate (backfill + gate)

The new Worker version now writes both the old and new columns. Enable
a feature flag that routes mobile and desktop clients to new code paths.

```typescript
// Feature flag in Worker env binding (wrangler.toml [vars])
const REPLY_COUNT_ENABLED = env.REPLY_COUNT_ENABLED === 'true';

// Backfill reply_count for existing posts (lazy or via scheduled Worker)
if (REPLY_COUNT_ENABLED) {
  await env.DB.prepare(`
    UPDATE posts
    SET    reply_count = (
             SELECT COUNT(*) FROM post_replies WHERE post_id = posts.id
           )
    WHERE  reply_count IS NULL
    LIMIT  500
  `).run();
}
```

Run the backfill as a Cron Trigger in batches of 500 rows to avoid
D1's row budget limits per execution. Adjust `LIMIT` based on the D1
plan's `max_rows_written_per_query` limit.

### Phase 3: Contract (drop old column / enforce NOT NULL)

Only after all Workers are confirmed running the new code (check
Workers observability for old version instance count = 0), apply the
final DDL that removes backward compatibility.

```sql
-- SQLite does not support DROP COLUMN before 3.35.
-- D1 (based on SQLite 3.44+) supports it:
ALTER TABLE posts DROP COLUMN legacy_sort_key;

-- Enforce NOT NULL now that all rows are backfilled:
-- SQLite cannot ALTER a column to NOT NULL; recreate the table.
-- Use the shadow-table swap pattern:
CREATE TABLE posts_new (
  id           TEXT    PRIMARY KEY,
  body         TEXT    NOT NULL,
  community_id TEXT    NOT NULL REFERENCES communities(id),
  created_at   INTEGER NOT NULL,
  reply_count  INTEGER NOT NULL DEFAULT 0  -- now NOT NULL
);
INSERT INTO posts_new SELECT id, body, community_id, created_at,
                              COALESCE(reply_count, 0)
FROM posts;
DROP TABLE posts;
ALTER TABLE posts_new RENAME TO posts;
```

The shadow-table swap acquires an exclusive lock for the duration of
the INSERT—run it during a low-traffic window or in a maintenance
Cron Trigger.

## Feature Flags for Column Rollout

Store feature flags in Wrangler environment variables or a KV namespace
to enable zero-config rollback without a Worker redeploy:

```toml
# wrangler.toml
[vars]
REPLY_COUNT_ENABLED = "false"

[env.production.vars]
REPLY_COUNT_ENABLED = "true"
```

```typescript
// Worker: gate new column reads behind the flag
function selectPostFields(env: Env): string {
  const base = 'id, body, community_id, created_at, score';
  return env.REPLY_COUNT_ENABLED === 'true'
    ? `${base}, reply_count`
    : base;
}
```

Flip the flag via `wrangler deploy --var REPLY_COUNT_ENABLED:true`
without touching the Worker code. This separates schema rollout from
code deployment.

## Mobile Client Schema Mismatch Handling

Mobile apps (React Native, PWA) may cache API responses or bundle
schema assumptions in client-side code. Version the API response shape:

```typescript
// API response versioning via Accept-Version header
const clientVersion = request.headers.get('X-Client-Version') ?? '1';

const post =
  Number(clientVersion) >= 2
    ? { ...basePost, replyCount: row.reply_count ?? 0 }
    : basePost; // v1 clients never see reply_count
```

For mobile apps that cannot be force-updated, maintain the old response
shape for at least two app release cycles (typically 4–6 weeks) before
contracting the schema.

If a mobile client sends a request with a column value the current
schema does not yet have (e.g. during a rollback), the Worker must
silently drop the unknown field rather than propagating a D1 error:

```typescript
// Defensive insert: only include known columns
const knownFields = ['id', 'body', 'community_id', 'created_at'];
if (env.REPLY_COUNT_ENABLED === 'true') knownFields.push('reply_count');

const placeholders = knownFields.map(() => '?').join(', ');
await env.DB.prepare(
  `INSERT INTO posts (${knownFields.join(', ')}) VALUES (${placeholders})`
).bind(...knownFields.map(f => payload[f])).run();
```

## Wrangler Migration File Convention

```
migrations/
  0001_create_posts.sql
  0002_add_communities.sql
  0003_expand_reply_count.sql      ← Phase 1 (nullable ADD COLUMN)
  0004_enforce_reply_count_nn.sql  ← Phase 3 (shadow-table swap)
```

Apply only Phase 1 before Worker deploy; commit Phase 3 to the
migration file but do not apply it until Phase 2 backfill is complete.
Use a CI gate that checks the feature flag before running Phase 3:

```bash
# CI/CD gate script
if [ "$REPLY_COUNT_BACKFILL_DONE" = "true" ]; then
  wrangler d1 migrations apply example project_DB --env production
fi
```

## Anti-Patterns

- Deploying DDL and Worker code simultaneously via a single CI step—
  there is always a propagation gap where old Workers run against new
  schema or vice versa.
- Adding a NOT NULL column without a DEFAULT in Phase 1; old Workers
  cannot insert rows without supplying the new column value.
- Performing the shadow-table swap during peak traffic hours—the
  exclusive lock blocks all concurrent reads.
- Removing a column before confirming all Worker instances have been
  upgraded—check `wrangler versions list` for running version counts.
- Encoding schema assumptions in mobile client bundles without an API
  version header mechanism; forces an emergency app update on schema
  change.

## Gotchas

- D1 does not support `ALTER TABLE ... MODIFY COLUMN` or
  `ALTER TABLE ... RENAME COLUMN` in all SQLite modes. Use the
  shadow-table swap for type or nullability changes.
- The shadow-table swap is not atomic from the application perspective:
  between `DROP TABLE posts` and `ALTER TABLE posts_new RENAME TO posts`
  there is a brief window where the table does not exist. Wrap in a
  transaction:
  ```sql
  BEGIN;
    ALTER TABLE posts RENAME TO posts_old;
    ALTER TABLE posts_new RENAME TO posts;
    DROP TABLE posts_old;
  COMMIT;
  ```
- D1 Wrangler migrations are applied sequentially and tracked in a
  `d1_migrations` table. Do not manually edit that table or skip
  migration files.
- Feature flags stored in `wrangler.toml` `[vars]` are baked at deploy
  time, not runtime-changeable without redeploy. Use KV for truly
  runtime-configurable flags.
- D1 read replicas may lag behind the primary by up to a few seconds
  after DDL changes. Wait at least 10 s after applying DDL before
  routing read traffic to replicas.

## Verification

```bash
# Phase 1: confirm new column exists and is nullable
wrangler d1 execute example project_DB --command \
  "SELECT name, type, notnull FROM pragma_table_info('posts')
   WHERE name = 'reply_count';"
# Expected: reply_count | INTEGER | 0 (not null = false)

# Phase 3: confirm NOT NULL enforcement
wrangler d1 execute example project_DB --command \
  "SELECT name, type, notnull FROM pragma_table_info('posts')
   WHERE name = 'reply_count';"
# Expected: reply_count | INTEGER | 1 (not null = true)

# Confirm no old Worker version still running:
wrangler versions list --env production
# All traffic should be on the latest version before Phase 3.
```

## Related

- `database/d1-migrations-wrangler-ci-cd.md`
- `database/backward-compatible-migrations.md`
- `database/zero-downtime-migrations.md`
- `database/d1-schema-versioning-wrangler-migrations.md`
- `database/migration-rollback-strategy.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://www.sqlite.org/lang_altertable.html
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/workers/wrangler/commands/#versions
