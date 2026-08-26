# Workers D1 Pre-Deploy Migration Safety Checks

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A migration that drops a column runs against the production D1 database before
the new Worker version reaches 100% traffic, causing the still-running old
Worker instances to return 500 errors for every query that references the
removed column. The old version cannot fall back because the column is gone and
D1 does not support transactional DDL rollback in the same way as PostgreSQL.

## Context

Cloudflare D1 uses SQLite semantics: DDL statements are not transactional with
DML in the same atomic unit, and there is no `pg_dump`-style hot backup before
a migration. Safe D1 migration deployment requires: (1) dry-run schema
inspection before any write, (2) a forward-compatible migration sequence that
the current Worker version can tolerate, (3) a local D1 integration test
against a migration preview database, and (4) a verified rollback SQL file
committed alongside every migration. These checks should run as a mandatory CI
gate before `wrangler deploy` is allowed to proceed.

## Pre-Flight Schema Inspection

Before applying any migration, diff the declared schema against the live
production schema to detect unexpected drift and ensure the migration is
additive.

```typescript
// scripts/d1-preflight.ts
import { execSync } from "child_process";

interface Column {
  cid: number;
  name: string;
  type: string;
  notnull: number;
  dflt_value: string | null;
  pk: number;
}

async function fetchLiveSchema(
  db: string,
  table: string
): Promise<Column[]> {
  const result = execSync(
    `npx wrangler d1 execute ${db} --env production --remote ` +
      `--command "PRAGMA table_info(${table});" --json`,
    { encoding: "utf8" }
  );
  const parsed = JSON.parse(result);
  return parsed[0]?.results ?? [];
}

async function detectDestructiveOps(migrationFile: string): Promise<string[]> {
  const { readFileSync } = await import("fs");
  const sql = readFileSync(migrationFile, "utf8").toUpperCase();

  const destructive: string[] = [];
  if (/DROP\s+COLUMN/.test(sql)) destructive.push("DROP COLUMN detected");
  if (/DROP\s+TABLE/.test(sql)) destructive.push("DROP TABLE detected");
  if (/ALTER\s+COLUMN/.test(sql)) destructive.push("ALTER COLUMN detected (SQLite rename workaround needed)");
  if (/NOT\s+NULL/.test(sql) && !/DEFAULT/.test(sql)) {
    destructive.push("NOT NULL without DEFAULT — will fail on existing rows");
  }
  return destructive;
}

async function preflight(migrationFile: string) {
  console.log(`Running pre-flight for: ${migrationFile}`);

  const issues = await detectDestructiveOps(migrationFile);
  if (issues.length > 0) {
    console.error("DESTRUCTIVE MIGRATION DETECTED:");
    issues.forEach((i) => console.error(`  - ${i}`));
    console.error(
      "Use a multi-phase migration: add column → deploy Worker → remove old column in next cycle."
    );
    process.exit(1);
  }

  // Verify rollback file exists alongside the migration
  const { existsSync } = await import("fs");
  const rollbackFile = migrationFile.replace(/\.sql$/, ".rollback.sql");
  if (!existsSync(rollbackFile)) {
    console.error(`MISSING rollback file: ${rollbackFile}`);
    process.exit(1);
  }

  console.log("Pre-flight passed.");
}

const migrationArg = process.argv[2];
if (!migrationArg) {
  console.error("Usage: npx tsx scripts/d1-preflight.ts <migration.sql>");
  process.exit(1);
}
await preflight(migrationArg);
```

## Local Integration Test Against D1 Preview

Before applying to remote, run the migration against a D1 preview database
(Cloudflare's non-production D1 copy) and execute the Worker's integration
test suite against it.

```typescript
// scripts/d1-migration-test.ts
import { execSync } from "child_process";

const DB_NAME = process.env.D1_DATABASE ?? "app-db";
const PREVIEW_DB = `${DB_NAME}-preview`;
const MIGRATION_DIR = "migrations";

function run(cmd: string): string {
  console.log(`$ ${cmd}`);
  return execSync(cmd, { encoding: "utf8", stdio: "pipe" });
}

async function testMigration() {
  // 1. Apply pending migrations to preview DB
  run(
    `npx wrangler d1 migrations apply ${PREVIEW_DB} --env staging --remote`
  );

  // 2. Run integration tests pointing at preview DB
  run(`npx vitest run --project integration`);

  // 3. Verify rollback SQL is valid syntax by applying it (then re-applying forward)
  const rollbackFiles = execSync(
    `ls ${MIGRATION_DIR}/*.rollback.sql 2>/dev/null || true`,
    { encoding: "utf8" }
  )
    .trim()
    .split("\n")
    .filter(Boolean);

  for (const rf of rollbackFiles) {
    console.log(`Testing rollback SQL validity: ${rf}`);
    run(
      `npx wrangler d1 execute ${PREVIEW_DB} --env staging --remote --file ${rf}`
    );
  }

  // 4. Re-apply forward to leave preview in a clean state
  run(
    `npx wrangler d1 migrations apply ${PREVIEW_DB} --env staging --remote`
  );

  console.log("Migration integration test passed.");
}

await testMigration();
```

## CI Gate Integrating All Safety Steps

```yaml
# .github/workflows/d1-migration-safety.yml
name: D1 Migration Safety
on:
  pull_request:
    paths:
      - "migrations/**"
      - "wrangler.toml"

jobs:
  migration-safety:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: "22" }

      - run: npm ci

      # Detect which migration files changed in this PR
      - name: Identify changed migrations
        id: migrations
        run: |
          FILES=$(git diff --name-only origin/main...HEAD -- 'migrations/*.sql' \
            | grep -v rollback || true)
          echo "files=$FILES" >> "$GITHUB_OUTPUT"

      # Run destructive-operation check on each changed migration
      - name: Pre-flight check
        if: steps.migrations.outputs.files != ''
        run: |
          for f in ${{ steps.migrations.outputs.files }}; do
            npx tsx scripts/d1-preflight.ts "$f"
          done
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

      # Integration test against preview D1
      - name: Integration test
        if: steps.migrations.outputs.files != ''
        run: npx tsx scripts/d1-migration-test.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          D1_DATABASE: app-db

      # Block merge until all checks pass — status is set by the job result
```

## Anti-patterns

- Running `wrangler d1 migrations apply --remote` on production in the same
  pipeline step as `wrangler deploy`; if deploy fails the migration has
  already run against live data with no simple undo path.
- Applying destructive migrations (DROP COLUMN) while the current Worker
  version still references that column; always decouple schema changes across
  two deploy cycles.
- Skipping the rollback SQL file requirement because "this migration is
  simple"; if the migration causes data issues the rollback file is the
  fastest recovery path.

## Gotchas

- D1's SQLite backend does not support transactional DDL; a `CREATE TABLE`
  inside a failed `BEGIN...COMMIT` block may partially succeed. Always test
  migrations against a preview database before production.
- `wrangler d1 migrations apply --dry-run` lists pending migrations but does
  not validate SQL syntax; use `d1 execute --command "EXPLAIN QUERY PLAN ..."`
  to validate before applying.

## Verification

```bash
# Dry-run list pending migrations without applying
npx wrangler d1 migrations list app-db --env production --remote

# Check schema drift between local definition and live DB
npx wrangler d1 execute app-db --env production --remote \
  --command "SELECT name, sql FROM sqlite_master WHERE type='table';" \
  | jq '.[] | .results'

# Manual pre-flight on a specific migration
npx tsx scripts/d1-preflight.ts migrations/0012_add_invoice_ref.sql
```

## Related

- `deploy/d1-schema-migration-sequencing-wrangler-remote.md`
- `deploy/database-migration-rollback-strategies.md`
- `deploy/pre-deploy-database-backup.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/platform/client-api/
- https://www.sqlite.org/lang_altertable.html
