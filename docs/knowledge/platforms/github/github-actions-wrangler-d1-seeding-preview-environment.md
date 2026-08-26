# GitHub Actions: Wrangler D1 Seeding for Preview Environments

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

PR preview deployments via `wrangler deploy --env preview` spin up isolated Workers but share
the same D1 databases unless you create per-PR databases. When a PR database is created fresh,
it is empty — migrations run but seed data does not follow. The result: the preview Worker
crashes on first request because required lookup tables or default configuration rows are absent.

## Context

Cloudflare Workers preview environments (one per PR, e.g. `worker-pr-42`) each need their own D1
database. Wrangler supports `wrangler d1 execute <db-name> --file seed.sql`, but the filename is
static; at CI time you need to:

1. Create a per-PR D1 database if it does not already exist.
2. Apply migrations in order via `wrangler d1 migrations apply`.
3. Apply seed data idempotently so force-pushes do not duplicate rows.
4. Bind the new database UUID to the preview Worker at deploy time.

This article focuses on the seeding and binding steps inside a GitHub Actions workflow.

## Workflow Setup

```yaml
# .github/workflows/preview.yml
name: Preview Deploy
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  preview:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    environment: preview
    env:
      DB_NAME: "myapp-pr-${{ github.event.pull_request.number }}"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile

      - name: Create or reuse D1 database
        run: pnpm tsx scripts/ensure-preview-db.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Run D1 migrations
        run: pnpm wrangler d1 migrations apply "$DB_NAME" --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Seed preview database
        run: pnpm tsx scripts/seed-preview-db.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy preview Worker with D1 binding
        run: |
          DB_UUID=$(pnpm tsx scripts/get-db-uuid.ts)
          pnpm wrangler deploy \
            --env preview \
            --name "myapp-pr-${{ github.event.pull_request.number }}" \
            --d1 "DB=$DB_UUID"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## ensure-preview-db.ts

Creates the per-PR D1 database if it does not exist; skips creation if it is already present.
This makes the step idempotent across force-pushes.

```typescript
// scripts/ensure-preview-db.ts
interface D1Database {
  uuid: string;
  name: string;
}

const DB_NAME = process.env.DB_NAME!;
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;

async function listD1Databases(): Promise<D1Database[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );
  const json = (await res.json()) as { result: D1Database[] };
  return json.result;
}

async function createD1Database(name: string): Promise<string> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name }),
    }
  );
  const json = (await res.json()) as { result: { uuid: string } };
  return json.result.uuid;
}

const databases = await listD1Databases();
const existing = databases.find((db) => db.name === DB_NAME);

if (existing) {
  console.log(`Reusing D1 database: ${DB_NAME} (${existing.uuid})`);
} else {
  const uuid = await createD1Database(DB_NAME);
  console.log(`Created D1 database: ${DB_NAME} (${uuid})`);
}
```

## get-db-uuid.ts

Resolves the database UUID by name; used to pass `--d1 DB=<uuid>` to `wrangler deploy`.

```typescript
// scripts/get-db-uuid.ts
const DB_NAME = process.env.DB_NAME!;
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database` +
    `?name=${encodeURIComponent(DB_NAME)}`,
  { headers: { Authorization: `Bearer ${API_TOKEN}` } }
);
const json = (await res.json()) as { result: { uuid: string }[] };
const uuid = json.result[0]?.uuid;
if (!uuid) {
  console.error(`D1 database not found: ${DB_NAME}`);
  process.exit(1);
}
// stdout is captured by $() in the workflow shell step
process.stdout.write(uuid);
```

## seed-preview-db.ts

Idempotent seeding via the D1 REST API. Uses `INSERT OR IGNORE` so re-runs on force-push never
create duplicate rows.

```typescript
// scripts/seed-preview-db.ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const DB_NAME = process.env.DB_NAME!;
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;

const SEED_SQL = readFileSync(
  resolve(process.cwd(), "db/seeds/preview.sql"),
  "utf-8"
);

interface D1QueryResult {
  success: boolean;
  errors: { code: number; message: string }[];
}

// Resolve UUID from name
const listRes = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database` +
    `?name=${encodeURIComponent(DB_NAME)}`,
  { headers: { Authorization: `Bearer ${API_TOKEN}` } }
);
const listJson = (await listRes.json()) as { result: { uuid: string }[] };
const uuid = listJson.result[0]?.uuid;
if (!uuid) throw new Error(`D1 database not found: ${DB_NAME}`);

// The REST API query endpoint accepts one SQL statement per request.
// Split on statement boundaries and execute sequentially.
const statements = SEED_SQL
  .split(";")
  .map((s) => s.trim())
  .filter(Boolean);

for (const sql of statements) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${uuid}/query`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ sql }),
    }
  );
  const result = (await res.json()) as D1QueryResult;
  if (!result.success) {
    console.error("Seed failed on statement:", sql);
    console.error(result.errors);
    process.exit(1);
  }
}

console.log(`Seeded ${statements.length} statements into ${DB_NAME}`);
```

## Idempotent Seed SQL

```sql
-- db/seeds/preview.sql
INSERT OR IGNORE INTO plans (id, name, monthly_price_cents)
VALUES
  ('free', 'Free', 0),
  ('pro',  'Pro',  1900),
  ('team', 'Team', 4900);

INSERT OR IGNORE INTO feature_flags (key, enabled)
VALUES
  ('new_dashboard', 1),
  ('beta_api',      0);
```

## Cleanup Workflow

Delete stale preview databases when a PR closes to avoid accumulating per-PR databases.

```yaml
# .github/workflows/preview-cleanup.yml
name: Preview Cleanup
on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    runs-on: ubuntu-latest
    env:
      DB_NAME: "myapp-pr-${{ github.event.pull_request.number }}"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm tsx scripts/delete-preview-db.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## Anti-patterns

- Running `INSERT` without `OR IGNORE` or `ON CONFLICT DO NOTHING` — every force-push re-seeds
  and multiplies rows.
- Creating the D1 database and running migrations in the same shell step — if the database already
  exists the create call fails with a non-zero exit code and the step errors before migrations run.
- Hardcoding a database UUID in `wrangler.toml` — the UUID is per-PR and must be resolved
  dynamically at CI time; commit the `[[ d1_databases ]]` binding with `database_name` only.
- Including the full production seed volume in `preview.sql` — seed only the minimum rows needed
  for the app to boot; large seeds slow every PR open and risk leaking real data shapes into logs.

## Gotchas

- `wrangler d1 migrations apply --remote` resolves the database by `database_name` in
  `wrangler.toml`, not by `$DB_NAME`. You must either patch `wrangler.toml` at CI time (fragile)
  or pass `--database-id <uuid>` with the UUID from `get-db-uuid.ts`.
- The D1 REST API `query` endpoint rejects multi-statement SQL strings. Split on `;` and execute
  each statement individually — but beware semicolons inside string literals.
- D1 database names are globally unique per Cloudflare account, not per project. Prefix with the
  repo slug: `myapp-pr-42`, not just `pr-42`.
- Wrangler `--d1 DB=<uuid>` overrides the binding at deploy time and does not persist to
  `wrangler.toml`. Re-run the deploy step with the same flag on every force-push to the PR.

## Verification

```bash
# Confirm seed rows exist in the preview DB
pnpm wrangler d1 execute myapp-pr-42 \
  --remote \
  --command "SELECT id, name, monthly_price_cents FROM plans ORDER BY id;"
```

Expected: three rows for `free`, `pro`, `team` with correct prices and no duplicates.

```bash
# Count rows to confirm idempotency across multiple runs
pnpm wrangler d1 execute myapp-pr-42 \
  --remote \
  --command "SELECT COUNT(*) AS n FROM plans;"
# Should always return n=3 regardless of how many times the seed step ran
```

## Related

- `github-actions-workers-preview-environments.md`
- `github-actions-cloudflare-d1-migration-pipeline.md`
- `github-actions-d1-snapshot-artifacts.md`
- `github-actions-dynamic-environment-variables-d1-config.md`

## Sources

- https://developers.cloudflare.com/d1/platform/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://developers.cloudflare.com/api/operations/cloudflare-d1-create-database
- https://developers.cloudflare.com/api/operations/cloudflare-d1-query-database
