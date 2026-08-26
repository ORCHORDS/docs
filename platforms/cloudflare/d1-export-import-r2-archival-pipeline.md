# D1 Export and Import Pipeline via R2 for Archival and Migration

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You run a production D1 database and need a reliable nightly backup that survives the 30-day retention window of Cloudflare's built-in point-in-time recovery. Occasionally you also need to clone the database into a staging environment or migrate data to a new D1 database created in another account. Manual `wrangler` commands run ad hoc are error-prone and leave no audit trail.

## Context

Cloudflare D1 exposes a REST API endpoint (`POST /d1/database/:id/export`) that generates a `.sql` dump asynchronously and returns a signed download URL. The dump can be uploaded to R2 immediately after download. R2 supports lifecycle rules that automatically delete objects after a configurable number of days, making it ideal for cost-controlled archival. A Cron Worker scheduled with `[triggers]` in `wrangler.toml` can orchestrate the full pipeline without any external infrastructure. Restoring into a new database uses `wrangler d1 import` locally, or the symmetric REST `POST /v4/accounts/:id/d1/database/:id/import` for programmatic workflows.

## Cron Worker — Nightly Export to R2

```typescript
// src/backup-worker.ts
export interface Env {
  R2_BACKUPS: R2Bucket;
  CF_ACCOUNT_ID: string;   // set via [vars] in wrangler.toml
  CF_API_TOKEN: string;    // set via secret: wrangler secret put CF_API_TOKEN
  D1_DATABASE_ID: string;  // set via [vars]
}

export default {
  // Triggered by cron schedule defined in wrangler.toml
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const timestamp = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
    const r2Key = `backups/d1/${timestamp}.sql`;

    // 1. Request an export from the D1 REST API
    const exportRes = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/d1/database/${env.D1_DATABASE_ID}/export`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ output_format: "polling" }),
      }
    );

    if (!exportRes.ok) {
      throw new Error(`Export request failed: ${exportRes.status} ${await exportRes.text()}`);
    }

    const { result } = (await exportRes.json()) as {
      result: { signed_url: string; filename: string };
    };

    // 2. Stream the SQL dump from the signed URL directly into R2
    const dumpRes = await fetch(result.signed_url);
    if (!dumpRes.ok || !dumpRes.body) {
      throw new Error(`Failed to download dump: ${dumpRes.status}`);
    }

    await env.R2_BACKUPS.put(r2Key, dumpRes.body, {
      httpMetadata: { contentType: "application/sql" },
      customMetadata: {
        databaseId: env.D1_DATABASE_ID,
        exportedAt: new Date().toISOString(),
      },
    });

    console.log(`Backup stored at r2://${r2Key}`);
  },
};
```

## wrangler.toml — Cron Trigger and R2 Binding

```toml
# wrangler.toml
name = "d1-backup-worker"
main = "src/backup-worker.ts"
compatibility_date = "2026-06-01"

[triggers]
crons = ["0 2 * * *"]  # 02:00 UTC every night

[[r2_buckets]]
binding = "R2_BACKUPS"
bucket_name = "db-backups"

[vars]
CF_ACCOUNT_ID = "your-account-id"
D1_DATABASE_ID = "your-d1-database-uuid"
# CF_API_TOKEN is set via: wrangler secret put CF_API_TOKEN
```

## R2 Lifecycle Rule for 90-day Retention

Lifecycle rules are set via the Cloudflare dashboard or REST API. There is no `wrangler` CLI shorthand yet.

```bash
# Create the bucket first
wrangler r2 bucket create db-backups

# Apply lifecycle rule via API (90-day expiry on backups/ prefix)
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/r2/buckets/db-backups/lifecycle" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [{
      "id": "expire-old-backups",
      "prefix": "backups/d1/",
      "enabled": true,
      "conditions": { "maxAgeSeconds": 7776000 }
    }]
  }'
# 7776000 s = 90 days
```

## Importing into a New D1 Database

```bash
# 1. Download the backup from R2
wrangler r2 object get db-backups/backups/d1/2026-08-24.sql \
  --file ./restore-2026-08-24.sql

# 2. Create the target database
wrangler d1 create my-database-restored
# Note the new database UUID printed in output

# 3. Import the SQL dump
wrangler d1 import my-database-restored \
  --local false \
  --file ./restore-2026-08-24.sql

# 4. Verify row counts (see Verification section)
```

## Verifying Import Integrity with Row Count Comparison

```bash
# Count rows in source database
wrangler d1 execute my-database \
  --command "SELECT name, (SELECT COUNT(*) FROM \"" || name || "\") as cnt FROM sqlite_master WHERE type='table' ORDER BY name;"

# Count rows in restored database — output must match
wrangler d1 execute my-database-restored \
  --command "SELECT name, (SELECT COUNT(*) FROM \"" || name || "\") as cnt FROM sqlite_master WHERE type='table' ORDER BY name;"

# Diff the two outputs — zero diff means integrity confirmed
diff <(wrangler d1 execute my-database --command "SELECT * FROM users ORDER BY id;") \
     <(wrangler d1 execute my-database-restored --command "SELECT * FROM users ORDER BY id;")
```

## Anti-patterns

- **Relying solely on D1 point-in-time recovery** — PITR has a limited window and is not portable across accounts; always maintain independent SQL dumps in R2 for true archival.
- **Storing the API token in `[vars]`** — plain vars are visible in the dashboard and logs; use `wrangler secret put` so the value is encrypted at rest.
- **Importing over an existing production database** — `wrangler d1 import` is destructive if the schema clashes; always import into a freshly created database first, verify, then swap the binding.
- **No checksum validation** — store an MD5 or SHA-256 of the dump as R2 object metadata at write time and verify it again before importing to catch silent corruption.

## Gotchas

- The `POST /d1/database/:id/export` REST endpoint returns a signed URL valid for a limited time (typically 1 hour). Download and upload to R2 within the same Worker invocation before the URL expires.
- Cron Workers have a CPU time limit of 30 seconds by default; very large databases may require a Durable Object or Queue-based pipeline to handle the streaming.
- `wrangler d1 import` does not support streaming from R2 directly — you must download the file locally first.
- D1 exports do not include virtual tables (FTS5, R*Tree); export those separately if used.
- The nightly cron fires in UTC; adjust the hour to match your low-traffic window in local time.

## Verification

```bash
# Confirm the backup object exists in R2
wrangler r2 object list db-backups --prefix backups/d1/

# Tail Worker logs to see the scheduled run
wrangler tail d1-backup-worker --format pretty

# Manually trigger a scheduled event locally
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+2+*+*+*"
```

## Related

- `workers-static-assets-spa-routing.md`
- `workers-tcp-socket-database-proxy.md`

## Sources

- Cloudflare D1 REST API reference — https://developers.cloudflare.com/api/resources/d1/
- wrangler d1 import / export CLI — https://developers.cloudflare.com/d1/wrangler-commands/
- R2 lifecycle rules — https://developers.cloudflare.com/r2/buckets/object-lifecycles/
