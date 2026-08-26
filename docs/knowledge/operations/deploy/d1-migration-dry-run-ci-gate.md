# D1 Migration Dry-Run CI Gate

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A destructive D1 migration (column drop, table rename, constraint change) reaches production and either breaks the live Worker or leaves the schema in an inconsistent state. The root cause is that migrations are applied directly without a pre-deploy validation step that would catch SQL errors, missing backfill steps, or compatibility regressions before traffic is affected.

## Context

Cloudflare D1 runs SQLite-compatible SQL migrations via `wrangler d1 migrations apply`. While wrangler validates migration file syntax locally, it does not catch runtime constraint violations, data-dependent failures, or ordering errors until the migration runs against the actual database. A dry-run CI gate applies the migration against a short-lived D1 clone or a dedicated CI database, validates the result, and blocks the deploy if the migration fails — all before any production schema change occurs.

---

## 1. CI Database Strategy

Maintain a dedicated `d1_ci` database for migration validation. It mirrors the production schema (populated from a schema export, not live data) and is reset before each CI run.

```toml
# wrangler.toml
[[d1_databases]]
binding      = "DB"
database_name = "my-app-prod"
database_id  = "aaaa-prod-uuid"

[env.ci]
[[env.ci.d1_databases]]
binding      = "DB"
database_name = "my-app-ci"
database_id  = "bbbb-ci-uuid"
```

```bash
# CI step: reset CI database to current production schema baseline
wrangler d1 execute my-app-ci --env ci --file ./migrations/schema-baseline.sql --remote
```

---

## 2. Dry-Run Migration Script

Apply pending migrations to the CI database and capture the exit code. Fail the pipeline if any migration errors.

```typescript
// scripts/d1-dry-run.ts
import { execSync, ExecSyncOptions } from 'child_process';

const CI_DB      = process.env.D1_CI_DATABASE_NAME ?? 'my-app-ci';
const MIGRATIONS = './migrations';

function run(cmd: string, opts: ExecSyncOptions = {}): string {
  return execSync(cmd, { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], ...opts });
}

// List pending migrations
const pending = run(
  `npx wrangler d1 migrations list ${CI_DB} --remote 2>&1`
);
console.log('Pending migrations:\n', pending);

if (pending.includes('No migrations to apply')) {
  console.log('No pending migrations — skipping dry-run gate');
  process.exit(0);
}

// Apply migrations to CI database
try {
  const result = run(
    `npx wrangler d1 migrations apply ${CI_DB} --remote 2>&1`
  );
  console.log('Dry-run output:\n', result);
  console.log('D1 dry-run PASSED');
} catch (err: unknown) {
  const msg = err instanceof Error ? err.message : String(err);
  console.error('D1 dry-run FAILED:\n', msg);
  process.exit(1);
}
```

---

## 3. Schema Snapshot Comparison Gate

After applying migrations to the CI database, compare the resulting schema against the expected schema snapshot committed in the repository. A diff indicates a missing or incorrect migration.

```typescript
// scripts/validate-d1-schema.ts
import { execSync } from 'child_process';
import { readFileSync, writeFileSync } from 'fs';

const CI_DB          = process.env.D1_CI_DATABASE_NAME ?? 'my-app-ci';
const SCHEMA_SNAPSHOT = './migrations/schema-snapshot.sql';

// Dump current schema from CI database
const actualSchema = execSync(
  `npx wrangler d1 execute ${CI_DB} --remote --command "SELECT sql FROM sqlite_master WHERE type IN ('table','index') ORDER BY name" --json`,
  { encoding: 'utf8' }
);

interface SchemaRow { sql: string }
const rows: SchemaRow[] = JSON.parse(actualSchema)[0]?.results ?? [];
const actualDump = rows.map((r) => r.sql).filter(Boolean).join('\n');

const expectedDump = readFileSync(SCHEMA_SNAPSHOT, 'utf8').trim();

if (actualDump.trim() !== expectedDump) {
  console.error('Schema mismatch after migration dry-run:');
  console.error('Expected:\n', expectedDump);
  console.error('Actual:\n', actualDump);
  // Write actual for diff visibility in CI logs
  writeFileSync('./migrations/schema-actual.sql', actualDump);
  process.exit(1);
}

console.log('Schema snapshot matches — gate PASSED');
```

---

## 4. Backfill Validation Query

For migrations that backfill data into a new column, run a validation query after the migration to confirm no rows were left with NULL where the constraint requires a value.

```typescript
// scripts/validate-d1-backfill.ts
const CI_DB    = process.env.D1_CI_DATABASE_NAME ?? 'my-app-ci';
const API_TOKEN = process.env.CF_API_TOKEN!;
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;

interface D1QueryResult {
  results: Record<string, unknown>[];
  success: boolean;
}

// Resolve database ID for the CI database
async function queryD1(databaseId: string, sql: string): Promise<D1QueryResult> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${databaseId}/query`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ sql, params: [] }),
    }
  );
  const json = await res.json() as { result: D1QueryResult[] };
  return json.result[0];
}

const CI_DB_ID = process.env.D1_CI_DATABASE_ID!;

const nullCheck = await queryD1(
  CI_DB_ID,
  `SELECT COUNT(*) as null_count FROM users WHERE new_required_column IS NULL`
);

const nullCount = nullCheck.results[0]?.null_count as number;
if (nullCount > 0) {
  console.error(`Backfill incomplete: ${nullCount} rows have NULL in new_required_column`);
  process.exit(1);
}

console.log('Backfill validation PASSED — no NULL rows found');
```

---

## 5. Full CI Gate Pipeline Step

Compose all validation steps into a single CI job that blocks the production deploy workflow.

```yaml
# .github/workflows/d1-migration-gate.yml
name: D1 Migration Dry-Run Gate

on:
  pull_request:
    paths:
      - 'migrations/**'
      - 'wrangler.toml'

jobs:
  d1-dry-run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Reset CI database to baseline
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler d1 execute my-app-ci \
            --file ./migrations/schema-baseline.sql \
            --remote

      - name: Apply migrations to CI database (dry-run)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          D1_CI_DATABASE_NAME: my-app-ci
        run: npx tsx scripts/d1-dry-run.ts

      - name: Validate schema snapshot
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          D1_CI_DATABASE_NAME: my-app-ci
        run: npx tsx scripts/validate-d1-schema.ts

      - name: Run backfill validation queries
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          D1_CI_DATABASE_ID: ${{ secrets.D1_CI_DATABASE_ID }}
        run: npx tsx scripts/validate-d1-backfill.ts
```

---

## 6. Schema Baseline Update Workflow

After each successful production migration, update the committed schema baseline so the next CI run resets to the correct state.

```typescript
// scripts/update-schema-baseline.ts
import { execSync } from 'child_process';
import { writeFileSync } from 'fs';

const PROD_DB   = process.env.D1_PROD_DATABASE_NAME ?? 'my-app-prod';
const PROD_DB_ID = process.env.D1_PROD_DATABASE_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${PROD_DB_ID}/query`,
  {
    method: 'POST',
    headers: { Authorization: `Bearer ${API_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ sql: "SELECT sql FROM sqlite_master WHERE type IN ('table','index') ORDER BY name", params: [] }),
  }
);

const json = await res.json() as { result: Array<{ results: Array<{ sql: string }> }> };
const schemaSql = json.result[0].results.map((r) => r.sql).filter(Boolean).join(';\n');

writeFileSync('./migrations/schema-baseline.sql', schemaSql + ';\n');
writeFileSync('./migrations/schema-snapshot.sql', schemaSql);
console.log('Schema baseline updated from production');
```

---

## Anti-Patterns

- **Using `--local` for the dry-run** — local D1 uses a different SQLite file than the remote database; a migration that passes locally can still fail remotely due to existing data or index conflicts.
- **Skipping the baseline reset** — without resetting the CI database, accumulated state from previous runs causes false migration conflicts or hides idempotency issues.
- **Gating only on syntax errors** — `wrangler d1 migrations apply` will parse SQL correctly but still fail at runtime on constraint violations or missing referenced tables; always run the actual apply against a CI database.
- **Committing production data to the baseline** — the CI database should contain only schema DDL, never real user data.

## Gotchas

- D1 does not support SQLite `ALTER TABLE DROP COLUMN` on older compatibility dates; verify your `compatibility_date` before writing destructive migrations.
- `wrangler d1 migrations apply --remote` runs synchronously but the D1 API may return before replication is complete. Add a 5-second wait before running validation queries against the CI database.
- The `sqlite_master` table query returns `NULL` for certain auto-generated indexes; filter these out with `WHERE sql IS NOT NULL` to keep schema snapshots clean.
- Migration files must be numbered sequentially without gaps; a missing file number causes `wrangler d1 migrations apply` to stop silently at the gap.

## Verification

1. Introduce a deliberate SQL syntax error in a test migration and confirm the CI gate fails with a non-zero exit code.
2. Confirm the gate blocks the PR merge via the required status check configured in branch protection.
3. After a successful dry-run, apply the same migrations to production and verify `wrangler d1 migrations list` shows no pending migrations.
4. Run `wrangler d1 execute my-app-prod --command "PRAGMA integrity_check" --remote` post-deploy to confirm database consistency.

## Related

- `d1-schema-migration-sequencing-wrangler-remote.md`
- `workers-d1-pre-deploy-migration-safety.md`
- `database-migration-deploy-strategy.md`
- `zero-downtime-database-migrations.md`
- `deploy-artifact-build-parity-ci-gate.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://developers.cloudflare.com/d1/reference/local-development/
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
