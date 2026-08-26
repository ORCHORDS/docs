# D1 Time Travel Database Recovery: What We Learned

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A migration bug in our D1-backed SaaS deleted the `price_overrides` column from the `subscriptions` table instead of the `legacy_price` column. The mistake was committed and deployed before anyone noticed. By the time we investigated:

- 4 hours of live traffic had written to the database without the column
- ~1 200 subscription records were affected
- A partial reload from a nightly backup would have caused duplicate charges

We used D1's Time Travel feature to recover. This article documents the process, what worked, what did not, and how we've hardened our recovery posture since.

---

## Context

D1 Time Travel allows you to restore a D1 database to any point within the last **30 days** using point-in-time bookmarks. A bookmark is an opaque string representing a specific state of the database WAL (write-ahead log).

Key facts:

- **30-day window**: writes older than 30 days are not recoverable via Time Travel.
- **Bookmarks are immutable**: once created they do not expire within the 30-day window.
- **Restore creates a new database**: restoring from a bookmark clones the database to a new D1 instance — it does not modify the source database in place unless you explicitly rename/rebind.
- **Time Travel covers schema and data**: the restored snapshot includes the table structure at that point in time.
- **Time Travel does not cover**: KV, R2, or Durable Objects that your Worker reads alongside D1. Those must be recovered separately.
- **Billing**: the restored database is a new D1 instance; it accrues normal D1 storage costs.

---

## Solution

### 1. Creating a pre-migration bookmark (the habit we now follow)

Before every destructive migration, create a Time Travel bookmark and record it in our migration log:

```typescript
// scripts/pre-migration-bookmark.ts
// Run via: npx ts-node scripts/pre-migration-bookmark.ts

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const DATABASE_ID = process.env.D1_DATABASE_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

async function createBookmark(): Promise<string> {
  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${DATABASE_ID}/time_travel/bookmark`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
      },
    },
  );

  if (!response.ok) {
    throw new Error(`Failed to create bookmark: ${response.status} ${await response.text()}`);
  }

  const { result } = await response.json<{ result: { bookmark: string } }>();
  return result.bookmark;
}

async function main(): Promise<void> {
  const bookmark = await createBookmark();
  const label = `pre-migration-${new Date().toISOString().replace(/[:.]/g, '-')}`;

  console.log(`Bookmark created: ${bookmark}`);
  console.log(`Record this in your migration log as: ${label}`);

  // Append to a local migration bookmark log
  const fs = await import('fs/promises');
  await fs.appendFile(
    '.migration-bookmarks',
    `${label}\t${bookmark}\n`,
  );
}

main().catch(console.error);
```

### 2. Restoring to a new database

```typescript
// scripts/restore-from-bookmark.ts

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const DATABASE_ID = process.env.D1_DATABASE_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

interface RestoreResult {
  database_id: string;
  name: string;
}

async function restoreToNewDatabase(
  bookmark: string,
  targetName: string,
): Promise<RestoreResult> {
  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${DATABASE_ID}/time_travel/restore`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        bookmark,
        // Restore to a new database — never restore in-place until validated
        target_database_name: targetName,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(`Restore failed: ${response.status} ${await response.text()}`);
  }

  const { result } = await response.json<{ result: RestoreResult }>();
  return result;
}

async function main(): Promise<void> {
  const bookmark = process.argv[2];
  if (!bookmark) throw new Error('Usage: ts-node restore-from-bookmark.ts <bookmark>');

  const targetName = `recovery-${Date.now()}`;
  console.log(`Restoring to new database: ${targetName}`);

  const result = await restoreToNewDatabase(bookmark, targetName);
  console.log(`Restored database ID: ${result.database_id}`);
  console.log('Validate the restored database before rebinding your Worker.');
}

main().catch(console.error);
```

### 3. Validating the restored database before cutover

```typescript
// scripts/validate-restored-db.ts
// Connect to the RESTORED database and run sanity checks before rebinding.

import { Kysely } from 'kysely';
// Using a D1 HTTP adapter for local validation scripts

async function validateRestoredDatabase(databaseId: string): Promise<void> {
  const checks = [
    {
      name: 'subscriptions table exists with price_overrides column',
      query: "SELECT price_overrides FROM subscriptions LIMIT 1",
    },
    {
      name: 'row count is plausible',
      query: 'SELECT COUNT(*) as cnt FROM subscriptions',
      minValue: 1000,
    },
    {
      name: 'no null price_overrides in active subscriptions',
      query: "SELECT COUNT(*) as cnt FROM subscriptions WHERE status = 'active' AND price_overrides IS NULL",
      maxValue: 0,
    },
  ];

  for (const check of checks) {
    try {
      const response = await queryD1(databaseId, check.query);
      console.log(`PASS: ${check.name}`, response);
    } catch (err) {
      console.error(`FAIL: ${check.name}`, err);
      process.exit(1);
    }
  }

  console.log('All validation checks passed. Safe to rebind Worker.');
}

async function queryD1(databaseId: string, sql: string): Promise<unknown> {
  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${process.env.CF_ACCOUNT_ID}/d1/database/${databaseId}/query`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ sql }),
    },
  );
  if (!response.ok) throw new Error(`Query failed: ${await response.text()}`);
  return response.json();
}

validateRestoredDatabase(process.argv[2]).catch(console.error);
```

### 4. Rebinding the Worker to the recovered database

After validation, update `wrangler.toml` to point to the recovered database ID and redeploy:

```toml
# wrangler.toml — after recovery
[[d1_databases]]
binding = "DB"
database_name = "production-db"
# Changed from original ID to the recovered database ID:
database_id = "<recovered-database-id>"
```

Then deploy:

```bash
# From your CI/CD pipeline — NOT via Claude in production
npx wrangler deploy
```

---

## Implementation Details

### What Time Travel does NOT cover

| System | Covered by Time Travel? | Recovery approach |
|--------|------------------------|-------------------|
| D1 data and schema | Yes | Restore from bookmark |
| KV values | No | Restore from exported JSON snapshot |
| R2 objects | No | R2 versioning (if enabled) or backups |
| Durable Objects storage | No | DO-level export + reimport |
| Queue messages | No | Not recoverable; design for idempotency |

### Testing the restore procedure

We run a monthly drill:

1. Create a bookmark of the production database.
2. Restore it to a `drill-<date>` database.
3. Run the validation script against the drill database.
4. Confirm row counts and schema match.
5. Immediately delete the drill database to avoid storage cost accumulation.

### Backup strategy beyond Time Travel

Time Travel's 30-day window is not a backup strategy — it is a recovery tool. Our full backup posture:

- **Daily export**: a Cron Worker runs `SELECT * FROM <table>` exports and stores compressed NDJSON to R2 with a 90-day lifecycle rule.
- **Pre-migration bookmark**: recorded in version control alongside every migration file.
- **Weekly restore drill**: automated via a Cron Worker that validates the most recent R2 export.

```typescript
// workers/src/d1-daily-export.ts

interface Env {
  DB: D1Database;
  BACKUP_BUCKET: R2Bucket;
}

const TABLES = ['subscriptions', 'users', 'orders', 'products'];

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const date = new Date().toISOString().slice(0, 10);

    for (const table of TABLES) {
      const { results } = await env.DB.prepare(`SELECT * FROM ${table}`).all();
      const ndjson = results.map(row => JSON.stringify(row)).join('\n');

      await env.BACKUP_BUCKET.put(
        `backups/${date}/${table}.ndjson`,
        ndjson,
        {
          httpMetadata: { contentType: 'application/x-ndjson' },
          customMetadata: { exportedAt: new Date().toISOString(), rowCount: String(results.length) },
        },
      );

      console.log(`Exported ${results.length} rows from ${table}`);
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Restoring in-place immediately**: always restore to a new database first, validate, then rebind. An in-place restore with a bad bookmark leaves you with no production database.
- **Not creating pre-migration bookmarks**: Time Travel lets you target any point in time, but having an explicit bookmark removes ambiguity during a stressful incident.
- **Assuming Time Travel covers your entire stack**: KV, R2, and DOs are NOT included. A column drop that also triggered a cascade into KV cache or R2-stored documents requires separate recovery for those systems.
- **Keeping restored databases permanently**: each restored database accrues storage billing. Delete drill databases after validation.
- **Using Time Travel as your only backup**: 30 days is not long enough for compliance, legal holds, or silent data corruption discovered late.

---

## Gotchas

- The `time_travel/restore` endpoint is asynchronous — the API returns a job ID, not an immediate result. Poll for completion before attempting to query the restored database.
- Restoring a very large database (>10 GB) can take 10–30 minutes. Plan for this in your runbook.
- The bookmark created by `POST /time_travel/bookmark` represents the state at the moment of the API call, not "now minus some delay". Create it as close to the migration as possible.
- A restored database does not inherit bindings, secrets, or `wrangler.toml` settings. Rebinding must be done manually.
- If you create a bookmark and then immediately write to the database, the bookmark still captures the state at creation time. Writes after the bookmark are not included.

---

## Verification

```bash
# Verify a bookmark was created and is valid (Wrangler CLI)
npx wrangler d1 time-travel info <database-name> --bookmark <bookmark-string>

# List recent backups in R2
npx wrangler r2 object list <backup-bucket> --prefix "backups/" --delimiter "/"
```

```typescript
// tests/backup-export.test.ts
import { describe, it, expect } from 'vitest';
import { env } from 'cloudflare:test';

describe('D1 daily export', () => {
  it('exports all tables to R2', async () => {
    // Seed test data
    await env.DB.prepare("INSERT INTO users (id, email) VALUES (1, 'test@example.com')").run();

    // Run the scheduled export
    const { default: worker } = await import('../src/d1-daily-export');
    await worker.scheduled?.({} as ScheduledEvent, env, {} as ExecutionContext);

    // Verify R2 object exists
    const today = new Date().toISOString().slice(0, 10);
    const obj = await env.BACKUP_BUCKET.head(`backups/${today}/users.ndjson`);
    expect(obj).not.toBeNull();
    expect(Number(obj?.customMetadata?.['rowCount'])).toBeGreaterThan(0);
  });
});
```

---

## Related

- `documentation/docs/policies/lessons/d1-transaction-isolation-lessons.md`
- `documentation/docs/policies/lessons/workers-durable-objects-storage-lessons.md`
- `documentation/docs/policies/lessons/r2-multipart-upload-lessons.md`

---

## Sources

- D1 Time Travel: https://developers.cloudflare.com/d1/reference/time-travel/
- D1 REST API: https://developers.cloudflare.com/api/operations/cloudflare-d1-create-database
- D1 limits: https://developers.cloudflare.com/d1/platform/limits/
- Wrangler D1 CLI: https://developers.cloudflare.com/workers/wrangler/commands/#d1
