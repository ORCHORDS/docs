# D1 Schema Migration Rollback Failure in Production

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A schema migration deployed to the example project production D1 database added a `NOT NULL` column without a default, which broke all write paths for anonymous post creation within minutes of rollout. The on-call engineer attempted to roll back by reverting the Wrangler migration state but discovered no rollback (`down`) script had been authored, leaving the database in a broken forward state. The incident lasted 47 minutes before a manual forward-fix migration was authored and applied under pressure.

## Context

example project's content layer uses a Cloudflare D1 database (`example project-posts-prod`) accessed exclusively through a Durable Object coordinator (`PostCoordinator`). The migration toolchain is Wrangler's built-in `wrangler d1 migrations` system. At the time of the incident, the team had a convention of writing `up` migration scripts only; `down` scripts were considered optional and had never been enforced in CI. The failing migration (`0041_add_moderation_verdict_column.sql`) added a `verdict TEXT NOT NULL` column to the `posts` table without a default value. All existing rows became immediately invalid for any `INSERT` that touched the table due to SQLite's strict mode being enabled on the D1 instance.

The team had 14 prior migrations deployed with no issues, which created false confidence in the migration process. No blue-green migration strategy was in place; migrations ran directly against the live database on deploy.

## Timeline

- **14:02 UTC** — Engineer merges PR #<number> (`feat: moderation verdict column`) to `main`. CI passes. GitHub Actions triggers automated deploy.
- **14:04 UTC** — `wrangler d1 migrations apply example project-posts-prod --remote` runs in CI. Migration `0041` applies successfully. Wrangler reports `1 migration applied`.
- **14:06 UTC** — First error alert fires: `PostCoordinator` returning `500` on `POST /posts`. PagerDuty page sent to on-call.
- **14:08 UTC** — On-call acknowledges. Begins investigation via Workers tail logs. Sees `NOT NULL constraint failed: posts.verdict` repeated across all write operations.
- **14:11 UTC** — On-call identifies root cause: migration `0041`. Attempts rollback via `wrangler d1 migrations apply example project-posts-prod --remote --rollback`.
- **14:13 UTC** — Wrangler rollback fails: `Error: No down migration found for 0041_add_moderation_verdict_column.sql`. On-call checks repo — no `down` file exists.
- **14:17 UTC** — Incident commander joins bridge. Decision made: write a forward-fix migration rather than attempt manual SQL surgery.
- **14:21 UTC** — Engineer drafts `0042_fix_verdict_column_nullable.sql` locally: `ALTER TABLE posts ALTER COLUMN verdict DROP NOT NULL;` — D1 rejects this; SQLite does not support `ALTER COLUMN`.
- **14:29 UTC** — Second attempt: engineer authors proper SQLite column rebuild migration using table rename + recreate pattern.
- **14:38 UTC** — Fix migration `0042` tested against staging D1 instance. Passes.
- **14:43 UTC** — Migration `0042` applied to production. Write errors cease.
- **14:49 UTC** — All `PostCoordinator` instances healthy. Incident closed.
- **15:30 UTC** — Post-mortem kickoff.

## Root Cause

Two compounding causes:

1. **No `down` migration authored.** The Wrangler migration system tracks which migrations have been applied via an internal `d1_migrations` table, and the `--rollback` flag expects a corresponding `down` SQL file to exist at the time rollback is attempted. Since the team had no enforcement of `down` scripts, `0041` had only an `up` path.

2. **SQLite ALTER TABLE limitations not accounted for.** Even if a `down` script had been available, the naive rollback (`DROP COLUMN verdict`) would have worked. But the first forward-fix attempt failed because engineers assumed D1/SQLite supported `ALTER COLUMN`, which it does not. The correct remediation required the table-rebuild pattern, which takes longer to author correctly under pressure.

The absence of a migration safety gate in CI allowed the under-specified migration to reach production unchallenged.

## Fix / Resolution: Forward-Fix Migration with Table Rebuild

The production fix applied a forward migration (`0042`) that rebuilt the `posts` table to make `verdict` nullable with a default:

```typescript
// scripts/generate-fix-migration.ts
// Helper used to author 0042 safely off the crit path

const FIX_MIGRATION = `
-- 0042_fix_verdict_column_nullable.sql
-- Forward-fix: make verdict nullable with a sensible default
-- SQLite does not support ALTER COLUMN; must rebuild the table.

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

-- Step 1: rename the broken table
ALTER TABLE posts RENAME TO posts_old;

-- Step 2: recreate with corrected schema
CREATE TABLE posts (
  id          TEXT    PRIMARY KEY,
  author_hash TEXT    NOT NULL,
  body        TEXT    NOT NULL,
  created_at  INTEGER NOT NULL,
  verdict     TEXT    DEFAULT NULL   -- nullable, populated async by moderation
);

-- Step 3: copy all existing rows; set verdict to NULL for legacy rows
INSERT INTO posts (id, author_hash, body, created_at, verdict)
SELECT id, author_hash, body, created_at, NULL
FROM posts_old;

-- Step 4: recreate indexes
CREATE INDEX idx_posts_created_at ON posts (created_at DESC);
CREATE INDEX idx_posts_author_hash ON posts (author_hash);

-- Step 5: drop old table
DROP TABLE posts_old;

COMMIT;

PRAGMA foreign_keys = ON;
`.trim();

console.log(FIX_MIGRATION);
```

Going forward, every migration file must ship a companion down file. The CI gate enforces this:

```typescript
// scripts/check-migration-pairs.ts
// Run in CI: bun run scripts/check-migration-pairs.ts

import { readdirSync } from "fs";
import { join } from "path";

const MIGRATIONS_DIR = join(process.cwd(), "migrations");

const files = readdirSync(MIGRATIONS_DIR);
const upFiles = files.filter((f) => f.endsWith(".up.sql"));
const downFiles = new Set(files.filter((f) => f.endsWith(".down.sql")));

let exitCode = 0;

for (const up of upFiles) {
  const base = up.replace(".up.sql", "");
  const expectedDown = `${base}.down.sql`;
  if (!downFiles.has(expectedDown)) {
    console.error(`❌  Missing down migration: ${expectedDown}`);
    exitCode = 1;
  }
}

if (exitCode === 0) {
  console.log(`✅  All ${upFiles.length} migrations have paired down scripts.`);
}

process.exit(exitCode);
```

## Prevention Checklist

- [ ] Require both `.up.sql` and `.down.sql` files for every migration; block PR merge if either is missing
- [ ] Run `wrangler d1 migrations apply --preview` against a staging D1 instance in CI before any merge to `main`
- [ ] Test rollback in CI: apply up, verify writes succeed, apply down, verify writes succeed again
- [ ] Add a schema linter step that flags `NOT NULL` columns with no `DEFAULT` on tables that already have rows
- [ ] Document the SQLite `ALTER TABLE` rebuild pattern in the team runbook before the next migration season
- [ ] Gate production migration apply behind a manual approval step in GitHub Actions for schema-changing migrations

## Monitoring Gaps Identified

- No alert existed on D1 write error rate; only the `PostCoordinator` HTTP 500 rate was monitored, adding a 2-minute detection lag
- Wrangler migration apply output was swallowed by CI logs and not surfaced to a Slack channel; team had no real-time visibility that a migration had just run on production

## Anti-patterns

- Writing `up`-only migrations and treating `down` scripts as optional — in an automated deploy pipeline there is no "optional"; if rollback cannot be scripted it cannot be executed safely under pressure
- Assuming `ALTER COLUMN` works in SQLite/D1 — SQLite's `ALTER TABLE` support is limited to `ADD COLUMN` and `RENAME`; any column type or constraint change requires the full table-rebuild pattern

## Gotchas

- Wrangler's `--rollback` flag does not generate a rollback automatically; it expects a pre-authored `down` file at the path it derives from the migration name — if that file is absent, rollback is a no-op that errors
- D1's `d1_migrations` internal table records which migrations have been applied by filename, not content hash; renaming a migration file after apply will confuse state tracking and may cause double-apply or skip on the next run

## Verification

```bash
# Verify migration pair enforcement passes locally
bun run scripts/check-migration-pairs.ts

# Apply up migration to staging and verify write path
wrangler d1 migrations apply example project-posts-staging --remote
curl -X POST https://example project-staging.workers.dev/posts \
  -H "Content-Type: application/json" \
  -d '{"body":"smoke test post"}' | jq .

# Apply down migration to staging and verify write path still works
wrangler d1 migrations apply example project-posts-staging --remote --rollback
curl -X POST https://example project-staging.workers.dev/posts \
  -H "Content-Type: application/json" \
  -d '{"body":"post-rollback smoke test"}' | jq .

# Confirm production D1 migration state
wrangler d1 migrations list example project-posts-prod --remote
```

## Related

- `lessons/migrations-must-be-backward-compatible.md`
- `lessons/always-test-rollback-before-deploying.md`
- `lessons/d1-write-contention-viral-event-postmortem.md`
- `lessons/zero-downtime-deployment-workers.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://www.sqlite.org/lang_altertable.html
- https://developers.cloudflare.com/d1/platform/client-api/
