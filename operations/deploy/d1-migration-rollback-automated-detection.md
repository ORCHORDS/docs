# D1 Migration Rollback Automated Detection

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

After a D1 migration runs successfully at the SQL level, the application may still behave incorrectly — a renamed column breaks a query in a Worker, a dropped index causes p99 latency to spike, or a NOT NULL constraint added to an existing table with bad data causes inserts to fail silently. Without automated post-migration health checks, these failures surface only through user reports or SLO breaches minutes or hours later.

Automated post-migration detection closes this gap: a health-check Worker runs immediately after the migration completes, probes the database for expected invariants, and triggers an automatic rollback (by re-applying the reverse migration) if any check fails — all before traffic has a chance to reach the broken state at scale.

## Context

Cloudflare D1 does not provide native rollback of applied migrations. The standard practice is to maintain paired migration files (`0012_add_user_role.sql` and `0012_add_user_role.down.sql`) and apply the down migration on failure. Wrangler tracks migration state in the `d1_migrations` table in each D1 database.

The detection loop runs as a dedicated Cloudflare Worker (the "migration guardian") that is invoked from CI immediately after `wrangler d1 migrations apply`. It queries D1 through the Worker's D1 binding, runs assertion queries, and reports pass/fail to the CI pipeline. If it fails, the CI pipeline runs the down migration and re-reports.

## Migration Guardian Worker

The guardian Worker exposes a single endpoint (`/health`) that runs a battery of post-migration assertions against the bound D1 database.

```typescript
// workers/migration-guardian/src/index.ts
import type { D1Database } from "@cloudflare/workers-types";

export interface Env {
  DB: D1Database;
  MIGRATION_GUARDIAN_SECRET: string;
}

interface AssertionResult {
  name: string;
  passed: boolean;
  detail?: string;
}

async function runAssertions(db: D1Database): Promise<AssertionResult[]> {
  const results: AssertionResult[] = [];

  // 1. Required tables must exist
  const requiredTables = ["users", "sessions", "user_roles"];
  for (const table of requiredTables) {
    const row = await db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
      )
      .bind(table)
      .first<{ name: string }>();
    results.push({
      name: `table_exists:${table}`,
      passed: row !== null,
      detail: row ? undefined : `Table '${table}' not found in sqlite_master`,
    });
  }

  // 2. Required columns must exist with correct types
  const columnChecks: Array<{
    table: string;
    column: string;
    expectedType: string;
  }> = [
    { table: "users", column: "email", expectedType: "TEXT" },
    { table: "users", column: "created_at", expectedType: "INTEGER" },
    { table: "user_roles", column: "role", expectedType: "TEXT" },
  ];

  for (const { table, column, expectedType } of columnChecks) {
    const info = await db
      .prepare(`PRAGMA table_info(${table})`)
      .all<{ name: string; type: string }>();
    const col = info.results.find((r) => r.name === column);
    const passed = col !== undefined && col.type === expectedType;
    results.push({
      name: `column_type:${table}.${column}`,
      passed,
      detail: col
        ? `Expected ${expectedType}, got ${col.type}`
        : `Column '${column}' not found in table '${table}'`,
    });
  }

  // 3. Required indexes must exist
  const requiredIndexes = [
    { table: "users", index: "idx_users_email" },
    { table: "sessions", index: "idx_sessions_user_id" },
  ];
  for (const { table, index } of requiredIndexes) {
    const row = await db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND name=?"
      )
      .bind(table, index)
      .first<{ name: string }>();
    results.push({
      name: `index_exists:${index}`,
      passed: row !== null,
      detail: row ? undefined : `Index '${index}' on '${table}' not found`,
    });
  }

  // 4. Row-count sanity (ensure migration did not truncate data)
  const { count } = (await db
    .prepare("SELECT COUNT(*) as count FROM users")
    .first<{ count: number }>())!;
  results.push({
    name: "row_count:users_nonzero",
    passed: count > 0,
    detail: count === 0 ? "users table is empty after migration" : undefined,
  });

  // 5. Applied migration recorded in d1_migrations
  const lastMigration = await db
    .prepare(
      "SELECT name FROM d1_migrations ORDER BY applied_at DESC LIMIT 1"
    )
    .first<{ name: string }>();
  results.push({
    name: "migration_recorded",
    passed: lastMigration !== null,
    detail: lastMigration ? undefined : "No migration recorded in d1_migrations",
  });

  return results;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "GET" || new URL(request.url).pathname !== "/health") {
      return new Response("Not Found", { status: 404 });
    }

    // Require a shared secret so this endpoint is not publicly exploitable
    const authHeader = request.headers.get("X-Guardian-Secret");
    if (authHeader !== env.MIGRATION_GUARDIAN_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const assertions = await runAssertions(env.DB);
    const allPassed = assertions.every((a) => a.passed);
    const failures = assertions.filter((a) => !a.passed);

    return Response.json(
      {
        passed: allPassed,
        assertions,
        failures,
        timestamp: new Date().toISOString(),
      },
      { status: allPassed ? 200 : 422 }
    );
  },
};
```

## CI Orchestration with Automatic Rollback

```yaml
# .github/workflows/d1-migrate-and-verify.yml
name: D1 Migrate and Verify

on:
  push:
    branches: [main]
    paths:
      - "migrations/**"

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Wrangler
        run: npm install -g wrangler

      - name: Apply D1 migrations
        id: apply_migration
        run: |
          wrangler d1 migrations apply my-d1-database --remote 2>&1 | tee /tmp/migration.log
          echo "applied=true" >> $GITHUB_OUTPUT
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Run migration guardian health check
        id: health_check
        run: |
          RESPONSE=$(curl -sf \
            -H "X-Guardian-Secret: $GUARDIAN_SECRET" \
            "https://migration-guardian.my-workers.workers.dev/health")
          echo "$RESPONSE" | jq .
          PASSED=$(echo "$RESPONSE" | jq -r '.passed')
          echo "passed=$PASSED" >> $GITHUB_OUTPUT
          if [ "$PASSED" != "true" ]; then
            echo "::error::Migration health check failed"
            echo "$RESPONSE" | jq -r '.failures[] | "  FAIL: \(.name) — \(.detail)"'
          fi
        env:
          GUARDIAN_SECRET: ${{ secrets.MIGRATION_GUARDIAN_SECRET }}

      - name: Rollback on failure
        if: steps.health_check.outputs.passed == 'false'
        run: |
          echo "::warning::Applying down migration for rollback..."
          # Determine the failing migration number from the log
          LAST_MIGRATION=$(cat /tmp/migration.log | grep -oP '\d{4}_\S+(?=\.sql)' | tail -1)
          DOWN_FILE="migrations/${LAST_MIGRATION}.down.sql"
          if [ -f "$DOWN_FILE" ]; then
            wrangler d1 execute my-d1-database --remote --file "$DOWN_FILE"
            echo "::error::Rolled back migration: $LAST_MIGRATION"
          else
            echo "::error::No down migration found: $DOWN_FILE — manual intervention required"
          fi
          exit 1
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy Worker after successful migration
        if: steps.health_check.outputs.passed == 'true'
        run: wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## Down Migration Convention

Every forward migration must have a paired down migration. Enforce this with a pre-commit check.

```bash
#!/usr/bin/env bash
# .git/hooks/pre-commit
# Ensures every new forward migration has a paired down migration

set -euo pipefail

NEW_MIGRATIONS=$(git diff --cached --name-only --diff-filter=A | grep -E 'migrations/[0-9]{4}_.*\.sql$' | grep -v '\.down\.sql$' || true)

for f in $NEW_MIGRATIONS; do
  BASE="${f%.sql}"
  DOWN="${BASE}.down.sql"
  if ! git diff --cached --name-only | grep -q "$DOWN" && [ ! -f "$DOWN" ]; then
    echo "ERROR: Missing down migration for $f"
    echo "       Expected: $DOWN"
    exit 1
  fi
done
```

```sql
-- migrations/0012_add_user_role.sql (forward)
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer';
CREATE INDEX idx_users_role ON users(role);

-- migrations/0012_add_user_role.down.sql (reverse)
DROP INDEX IF EXISTS idx_users_role;
-- SQLite does not support DROP COLUMN before 3.35; use table rebuild pattern if needed
-- For SQLite 3.35+:
ALTER TABLE users DROP COLUMN role;
```

## Guardian Worker Deployment Configuration

```toml
# workers/migration-guardian/wrangler.toml
name = "migration-guardian"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "my-d1-database"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
# MIGRATION_GUARDIAN_SECRET is set as a Worker secret, not a var
```

```bash
# Deploy the guardian Worker (run once; it stays deployed)
wrangler secret put MIGRATION_GUARDIAN_SECRET --name migration-guardian
# Enter a random high-entropy string at the prompt

wrangler deploy --config workers/migration-guardian/wrangler.toml
```

## Anti-patterns

- Running the health check before the new Worker version is deployed — the Worker code may still reference old column names, making the check inaccurate
- Checking only SQL-level success (`wrangler d1 migrations apply` exit code 0) without verifying application-level invariants
- Using a public guardian endpoint without authentication — this exposes internal schema details
- Writing down migrations that are not the exact reverse of the forward migration (e.g. dropping a column whose default value has changed)
- Running the guardian from inside the same Worker being deployed — the guardian must be a separate deployment to avoid circular dependency

## Gotchas

- D1 SQLite does not support `DROP COLUMN` in SQLite versions below 3.35; Cloudflare D1 runs SQLite 3.46+ as of 2026, so this is safe, but always test down migrations in a staging D1 database first
- The `d1_migrations` table is created and managed by Wrangler; do not manually insert or delete rows from it
- `wrangler d1 execute --remote` bills against D1 read/write units — health check queries count toward your monthly quota
- If a migration runs partially (e.g. the connection drops mid-statement), `d1_migrations` may not record it but the schema may be partially changed — always use SQLite transactions in migrations (`BEGIN; ... COMMIT;`)
- The guardian Worker must be deployed in the same Cloudflare account and bound to the same D1 database as the production Worker

## Verification

1. After a successful migration, call the guardian endpoint manually: `curl -H "X-Guardian-Secret: $SECRET" https://migration-guardian.my-workers.workers.dev/health` and confirm `"passed": true`.
2. After a simulated failure (temporarily rename a required column in a staging DB), confirm the CI pipeline applies the down migration and exits non-zero.
3. Check `d1_migrations` table after rollback: `wrangler d1 execute my-d1-database --remote --command "SELECT * FROM d1_migrations ORDER BY applied_at DESC LIMIT 5"`.
4. Verify the Worker version deployed is consistent with the migration state by checking `wrangler versions list`.

## Related

- `d1-migration-dry-run-ci-gate.md` — dry-run validation before applying migrations
- `d1-schema-migration-sequencing-wrangler-remote.md` — sequencing migrations with Wrangler remote
- `database-migration-rollback-strategies.md` — general database rollback patterns
- `deployment-health-gates-automated-rollback.md` — health gate patterns for automated rollback

## Sources

- Cloudflare D1: Migrations: https://developers.cloudflare.com/d1/reference/migrations/
- Cloudflare Workers: D1 binding: https://developers.cloudflare.com/workers/runtime-apis/bindings/d1/
- SQLite ALTER TABLE documentation: https://www.sqlite.org/lang_altertable.html
