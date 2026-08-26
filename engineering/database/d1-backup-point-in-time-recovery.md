# D1 Backup and Point-in-Time Recovery Procedures
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A destructive migration, an errant bulk DELETE, or a schema corruption event leaves your D1
database in an unrecoverable state. You need to restore to a known-good checkpoint — ideally
to a specific point in time — without multi-hour downtime. Or you need offsite backups for
compliance purposes that Cloudflare's managed backups alone do not satisfy.

## Context

Cloudflare D1 (as of 2026) maintains internal automated backups with a multi-day retention
window, accessible only through the Cloudflare dashboard's "Restore" button. These backups
are opaque: you cannot inspect them, you cannot automate restoration programmatically, and
you cannot control snapshot cadence.

For production workloads that need faster recovery, custom snapshot cadence, or offsite
storage, a complementary backup strategy using R2 and Workers is required. This article
covers:

1. Snapshot exports using the D1 REST API export endpoint
2. Scheduled backups to R2 with timestamped keys
3. Point-in-time-style recovery using a change log in R2
4. Restore procedures (manual and semi-automated)

---

## Strategy 1 — Scheduled Snapshot Exports to R2

The D1 REST API provides a database export endpoint that streams a SQLite `.db` file. A
Cron Trigger Worker calls this endpoint and pipes the response to R2.

### Wrangler configuration

```toml
# wrangler.toml
name = "example project-backup"

[[d1_databases]]
binding = "DB"
database_name = "example project-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[r2_buckets]]
binding = "BACKUPS"
bucket_name = "example project-backups"

[triggers]
crons = ["0 2 * * *"]   # 02:00 UTC daily
```

### Worker export implementation

```typescript
// src/backup-worker.ts
import type { Env } from "./types";

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runBackup(env));
  },
} satisfies ExportedHandler<Env>;

async function runBackup(env: Env): Promise<void> {
  const accountId = env.CF_ACCOUNT_ID;
  const databaseId = env.D1_DATABASE_ID;
  const apiToken   = env.CF_API_TOKEN;

  // 1. Initiate export via REST API
  const initRes = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/export`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ output_format: "polling" }),
    }
  );

  if (!initRes.ok) {
    throw new Error(`Export init failed: ${initRes.status} ${await initRes.text()}`);
  }

  const { result } = await initRes.json<{ result: { at_bookmark: string; filename: string; status: string; signed_url?: string } }>();

  // 2. Poll until export is ready (usually < 30 s for small databases)
  let signedUrl = result.signed_url;
  let attempts = 0;
  while (!signedUrl && attempts < 20) {
    await new Promise((r) => setTimeout(r, 3_000));
    const pollRes = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/export`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ output_format: "polling", current_bookmark: result.at_bookmark }),
      }
    );
    const pollData = await pollRes.json<{ result: { signed_url?: string } }>();
    signedUrl = pollData.result.signed_url;
    attempts++;
  }

  if (!signedUrl) throw new Error("Export timed out after polling");

  // 3. Stream export file to R2
  const fileRes = await fetch(signedUrl);
  if (!fileRes.ok || !fileRes.body) throw new Error("Signed URL fetch failed");

  const now = new Date().toISOString().replace(/[:.]/g, "-");
  const r2Key = `snapshots/${now}.db`;

  await env.BACKUPS.put(r2Key, fileRes.body, {
    httpMetadata: { contentType: "application/x-sqlite3" },
    customMetadata: { source_database_id: databaseId, at_bookmark: result.at_bookmark },
  });

  console.log(`Backup written to R2: ${r2Key}`);

  // 4. Prune snapshots older than 30 days
  await pruneOldSnapshots(env, 30);
}

async function pruneOldSnapshots(env: Env, retainDays: number): Promise<void> {
  const cutoff = Date.now() - retainDays * 86_400_000;
  const listed = await env.BACKUPS.list({ prefix: "snapshots/" });

  for (const obj of listed.objects) {
    if (obj.uploaded.getTime() < cutoff) {
      await env.BACKUPS.delete(obj.key);
      console.log(`Pruned old snapshot: ${obj.key}`);
    }
  }
}
```

---

## Strategy 2 — Continuous Change Log for Point-in-Time Recovery

Snapshots give daily recovery points. For finer-grained recovery, append every mutation to
a JSON-L log in R2. Replaying the log up to a specific timestamp reconstructs any state
between snapshots.

```typescript
// src/change-log.ts
import type { Env } from "./types";

interface ChangeEntry {
  ts: number;      // Unix ms
  sql: string;
  params: unknown[];
}

export async function logChange(env: Env, sql: string, params: unknown[]): Promise<void> {
  const entry: ChangeEntry = { ts: Date.now(), sql, params };
  const line = JSON.stringify(entry) + "\n";

  // Append to a date-partitioned log file
  const dateKey = new Date().toISOString().slice(0, 10);  // "2026-08-22"
  const r2Key = `changelogs/${dateKey}.jsonl`;

  const existing = await env.BACKUPS.get(r2Key);
  const prevContent = existing ? await existing.text() : "";
  await env.BACKUPS.put(r2Key, prevContent + line, {
    httpMetadata: { contentType: "application/x-ndjson" },
  });
}
```

Note: R2 `put` is an overwrite, not an append. For high-frequency writes, batch entries in
a Durable Object queue and flush periodically to avoid R2 write amplification.

---

## Restore Procedures

### Restore from R2 snapshot (manual)

```bash
# 1. Download the snapshot from R2 using wrangler or the dashboard
npx wrangler r2 object get example project-backups/snapshots/2026-08-21T02-00-00-000Z.db \
  --file restore.db

# 2. Inspect the snapshot locally
sqlite3 restore.db ".tables"
sqlite3 restore.db "SELECT COUNT(*) FROM documents"

# 3. Import into a new D1 database (zero-downtime: restore to a shadow DB first)
npx wrangler d1 execute example project-db-restore \
  --file restore.db \
  --remote

# 4. Verify row counts match expectations, then swap the binding in wrangler.toml
```

### Semi-automated restore using the import API

```typescript
// src/restore.ts
// Run as a one-off Worker invocation via `wrangler dev --remote`

export async function restoreFromSnapshot(env: Env, r2Key: string): Promise<void> {
  const obj = await env.BACKUPS.get(r2Key);
  if (!obj) throw new Error(`Snapshot not found: ${r2Key}`);

  const accountId  = env.CF_ACCOUNT_ID;
  const databaseId = env.D1_RESTORE_DATABASE_ID;  // target shadow DB
  const apiToken   = env.CF_API_TOKEN;

  // Get a signed upload URL from D1 import API
  const initRes = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/import`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${apiToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ action: "init" }),
    }
  );
  const { result: { upload_url, filename } } = await initRes.json<any>();

  // Stream R2 object to the signed upload URL
  await fetch(upload_url, {
    method: "PUT",
    body: obj.body,
    headers: { "Content-Type": "application/x-sqlite3" },
  });

  // Trigger the import
  const importRes = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/import`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${apiToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ action: "ingest", filename }),
    }
  );
  const importData = await importRes.json<any>();
  console.log("Import result:", importData.result);
}
```

---

## Backup Verification

A backup you have not tested is not a backup. Run a weekly verification Cron:

```typescript
// src/verify-backup.ts
export async function verifyLatestSnapshot(env: Env): Promise<void> {
  const listed = await env.BACKUPS.list({ prefix: "snapshots/", limit: 1 });
  if (listed.objects.length === 0) {
    throw new Error("No snapshots found in R2");
  }

  const latest = listed.objects[0];
  const ageMs  = Date.now() - latest.uploaded.getTime();
  const ageHrs = ageMs / 3_600_000;

  if (ageHrs > 26) {
    // Backup is more than 26 hours old — alert
    await env.ALERT_QUEUE.send({
      type: "backup_stale",
      key: latest.key,
      age_hours: ageHrs,
    });
  }

  // Optionally: restore to an in-memory SQLite (via sqlite-wasm in a Worker)
  // and run a SELECT COUNT(*) on a known large table as a sanity check.
  console.log(`Latest snapshot: ${latest.key}, age: ${ageHrs.toFixed(1)}h, size: ${latest.size} bytes`);
}
```

---

## Anti-patterns

- **Relying solely on Cloudflare's managed backups**: They cannot be automated, scripted, or
  inspected. If a Cloudflare datacenter issue corrupts the backup, you have no recourse.

- **Overwriting the same R2 key on every backup**: Use timestamped keys so you have a history
  of snapshots to roll back through.

- **Restoring directly to production without a shadow test**: Always restore to a shadow D1
  database, verify data integrity, then switch the Worker binding.

- **Not storing the `at_bookmark`**: The bookmark in the export metadata identifies the
  consistent read snapshot. Storing it in R2 `customMetadata` lets you correlate the snapshot
  with the change log for precise PITR replay.

- **Appending to R2 with high frequency**: R2 has no native append. High-frequency change log
  writes must be buffered (Durable Object, Workers KV, or Queue) before flushing to R2.

---

## Gotchas

- **Export API rate limits**: The D1 export endpoint counts against your account's API rate
  limits. Daily snapshots are safe; more frequent snapshots risk throttling.

- **SQLite file format compatibility**: Restoring a snapshot exported from one D1 version to a
  database running a newer SQLite build is generally safe (SQLite is backward compatible), but
  confirm the SQLite version in your Worker's D1 binding hasn't changed a page format.

- **Change log replay ordering**: JSON-L logs are ordered by write time, but concurrent Workers
  may interleave writes. If strict ordering matters, include a sequence number from a
  Durable Object counter.

- **D1 import size limit**: The D1 import API has a maximum file size (check current docs;
  typically 10 GB as of 2026). Databases larger than this require a different migration path
  (e.g., streaming inserts via the SQL API).

---

## Verification

```bash
# List recent snapshots
npx wrangler r2 object list example project-backups --prefix snapshots/ | head -20

# Check snapshot metadata for at_bookmark
npx wrangler r2 object head example project-backups/snapshots/2026-08-21T02-00-00-000Z.db

# Verify change log date files
npx wrangler r2 object list example project-backups --prefix changelogs/ | tail -10
```

---

## Related

- `database-backup-strategies.md` — general backup theory and 3-2-1 rule
- `point-in-time-recovery.md` — PostgreSQL PITR for comparison
- `d1-batch-operations-performance.md` — bulk insert during restore
- `d1-migrations-wrangler-ci-cd.md` — migration state and schema versioning
- `sqlite-vacuum-into-backup-boundary.md` — `VACUUM INTO` as an alternative export mechanism

## Sources

- D1 Export API: https://developers.cloudflare.com/d1/reference/backups/
- D1 Import API: https://developers.cloudflare.com/d1/best-practices/import-export-data/
- R2 Workers bindings: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
