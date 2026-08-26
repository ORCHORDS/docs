# Pulumi Cloudflare D1 Database Backup Automation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

D1's built-in Time Travel retains snapshots for 30 days (paid plans) and lets you
restore to a point in time, but it is not a substitute for off-platform backups. A
regional Cloudflare incident, accidental data deletion, or an account-level API error
can make Time Travel unavailable or insufficient. Teams also need backups in R2 for
compliance export requirements that mandate object-storage retention beyond 30 days.
Provisioning the full backup stack — D1 database, a scheduled cron Worker that exports
rows to R2, and the cron trigger — via Pulumi keeps the entire setup reproducible across
environments.

## Context

D1 does not expose a native dump API from Workers; exports require using the REST API
(`POST /accounts/{id}/d1/database/{db_id}/export`) which streams a SQL dump. A cron
Worker can call the Cloudflare API using a stored API token, receive the dump stream,
and write the result to an R2 object. Pulumi provisions all three components:

1. **D1 Database** — `cloudflare.D1Database`
2. **R2 Backup Bucket** — `cloudflare.R2Bucket`
3. **Backup Worker** — `cloudflare.WorkerScript` with a cron trigger and R2 + secret
   bindings

The backup Worker runs on a cron schedule managed by `cloudflare.WorkerCronTrigger`,
provisioned through Pulumi alongside the Worker script.

## 1. Pulumi Stack Setup

```typescript
// index.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

const cfConfig = new pulumi.Config("cloudflare");
const accountId = cfConfig.require("accountId");
const stack = pulumi.getStack(); // "staging" | "production"

const config = new pulumi.Config();
const cfApiToken  = config.requireSecret("cfApiToken");   // token with D1:Read + R2:Edit
const backupCron  = config.get("backupCron") ?? "0 2 * * *"; // 02:00 UTC daily
```

## 2. D1 Database and R2 Backup Bucket

```typescript
// databases.ts
export const appDb = new cloudflare.D1Database("app-db", {
  accountId,
  name: `app-db-${stack}`,
}, {
  protect: stack === "production",
  retainOnDelete: stack === "production",
});

export const backupBucket = new cloudflare.R2Bucket("d1-backups", {
  accountId,
  name: `d1-backups-${stack}`,
  location: "WEUR",
});
```

## 3. Backup Worker Source

```typescript
// src/backup-worker.ts  (compiled to dist/backup-worker.js before pulumi up)

export interface Env {
  BACKUP_BUCKET: R2Bucket;
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  D1_DATABASE_ID: string;
}

interface R2Bucket {
  put(key: string, value: ReadableStream | ArrayBuffer | string): Promise<void>;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const objectKey = `backups/${timestamp}.sql`;

    // Trigger D1 export via Cloudflare REST API
    const exportRes = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}` +
      `/d1/database/${env.D1_DATABASE_ID}/export`,
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
      throw new Error(`D1 export initiation failed: ${exportRes.status}`);
    }

    const { result } = await exportRes.json<{ result: { at_bookmark: string; filename: string } }>();

    // Poll until the dump file is ready (usually < 10 s for small databases)
    const dumpUrl = await pollExportReady(
      env.CF_ACCOUNT_ID,
      env.D1_DATABASE_ID,
      result.at_bookmark,
      env.CF_API_TOKEN
    );

    // Stream the dump directly into R2
    const dumpRes = await fetch(dumpUrl);
    if (!dumpRes.ok || !dumpRes.body) {
      throw new Error(`Failed to fetch dump: ${dumpRes.status}`);
    }

    await env.BACKUP_BUCKET.put(objectKey, dumpRes.body);
    console.log(`D1 backup written to R2: ${objectKey}`);
  },
};

async function pollExportReady(
  accountId: string,
  dbId: string,
  bookmark: string,
  token: string,
  maxAttempts = 20
): Promise<string> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 3_000));

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
      `/d1/database/${dbId}/export`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ output_format: "polling", current_bookmark: bookmark }),
      }
    );
    const body = await res.json<{ result: { status: string; signed_url?: string } }>();

    if (body.result.status === "complete" && body.result.signed_url) {
      return body.result.signed_url;
    }
  }
  throw new Error("D1 export timed out after polling");
}
```

## 4. Pulumi Worker + Cron + Secret Bindings

```typescript
// backup-worker.ts (Pulumi)
import { appDb, backupBucket } from "./databases";

const backupWorker = new cloudflare.WorkerScript("d1-backup-worker", {
  accountId,
  name: `d1-backup-worker-${stack}`,
  content: new pulumi.asset.FileAsset("./dist/backup-worker.js"),
  module: true,

  r2BucketBindings: [{
    name: "BACKUP_BUCKET",
    bucketName: backupBucket.name,
  }],

  plainTextBindings: [
    { name: "CF_ACCOUNT_ID", text: accountId },
    { name: "D1_DATABASE_ID", text: appDb.id },
  ],

  secretTextBindings: [{
    name: "CF_API_TOKEN",
    text: cfApiToken,     // injected from pulumi config secret
  }],
});

// Cron trigger — runs daily at 02:00 UTC
new cloudflare.WorkerCronTrigger("d1-backup-cron", {
  accountId,
  scriptName: backupWorker.name,
  schedules: [{ cron: backupCron }],
});
```

## 5. R2 Lifecycle Rules for Backup Retention

```typescript
// lifecycle.ts
new cloudflare.R2BucketLifecycle("d1-backup-lifecycle", {
  accountId,
  bucketName: backupBucket.name,
  rules: [{
    id:      "expire-old-backups",
    enabled: true,
    prefix:  "backups/",
    expiration: {
      // Delete objects older than 90 days
      days: stack === "production" ? 90 : 14,
    },
  }],
});
```

## 6. Stack Outputs

```typescript
// outputs.ts
pulumi.export("d1DatabaseId",    appDb.id);
pulumi.export("d1DatabaseName",  appDb.name);
pulumi.export("backupBucketName", backupBucket.name);
pulumi.export("backupWorkerName", backupWorker.name);
```

## 7. Manual Trigger for On-Demand Backup

Outside of the cron schedule you can trigger the backup Worker immediately:

```bash
# Trigger the Worker via the Cloudflare API
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/d1-backup-worker-production/schedules" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"

# Or run it locally via wrangler for testing
wrangler dev dist/backup-worker.js --env production
```

## Anti-patterns

- **Writing backup files to the same D1 database** — if the database is corrupted or
  deleted, the backup index is lost too. Write backups to R2, not back to D1.
- **Using a high-privilege API token in the backup Worker** — the token needs only
  `D1:Read` + `R2:Edit` on the specific bucket. Scoping it broadly creates a privilege
  escalation vector if the Worker is compromised.
- **Polling in a tight loop without sleep** — D1 export polling counts as subrequests.
  A tight loop can exhaust the Worker's 1,000-subrequest budget. Always wait at least 3
  seconds between poll attempts.
- **Skipping restore testing** — a backup that has never been restored is an unknown
  quantity. Schedule a monthly restore test to a throw-away D1 database using the R2
  dump file.
- **Not pinning the Worker compatibility date** — add `compatibility_date` to the
  Worker or `wrangler.toml` to prevent runtime changes from breaking the export polling
  logic.

## Gotchas

- D1 export uses a polling model: the first `POST` initiates the export and returns a
  bookmark; subsequent `POST` calls with `current_bookmark` return either the dump URL
  or a pending status. The Workers `fetch` timeout (30 s per subrequest) means you
  should not wait more than ~25 s per poll cycle.
- Large D1 databases (> 2 GB) will time out the Worker's 30-second CPU limit if you
  try to buffer the entire dump in memory. Stream the response body directly into R2's
  `put()` call to avoid memory errors.
- The signed dump URL from the export API expires in 15 minutes. Do not cache it across
  invocations; always re-trigger the export to get a fresh URL.
- `WorkerCronTrigger` replaces all existing cron schedules on the Worker. If you add a
  second schedule entry, always include the original entry as well; omitting it
  effectively deletes the old cron.
- Pulumi `protect: true` on the D1 database prevents `pulumi destroy` but does not
  prevent deletion via the Cloudflare dashboard or API. Combine protection with IAM
  token scoping.

## Verification

```bash
# Confirm the cron trigger is registered
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/d1-backup-worker-production/schedules" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[].cron'

# List backup objects in R2
wrangler r2 object list "d1-backups-production" --prefix backups/ --limit 10

# Restore most recent backup to a test database
LATEST=$(wrangler r2 object list "d1-backups-production" --prefix backups/ --json \
  | jq -r '.objects | sort_by(.uploaded) | last | .key')
wrangler r2 object get "d1-backups-production" --key "$LATEST" --file /tmp/restore.sql
wrangler d1 execute app-db-restore --file /tmp/restore.sql
```

## Related

- `cloudflare-d1-time-travel-point-in-time-recovery.md` — built-in D1 Time Travel
- `cloudflare-d1-migrations-github-actions.md` — schema migration automation
- `pulumi-cloudflare-d1-database-iac.md` — D1 provisioning fundamentals
- `cloudflare-r2-backup-restore-strategy.md` — R2 backup architecture
- `workers-secrets-rotation-automation.md` — rotating the backup API token

## Sources

- D1 Export API: https://developers.cloudflare.com/api/operations/cloudflare-d1-export-d1-database
- D1 Time Travel: https://developers.cloudflare.com/d1/reference/time-travel/
- Pulumi `cloudflare.WorkerCronTrigger`: https://www.pulumi.com/registry/packages/cloudflare/api-docs/workercrontrigger/
- R2 lifecycle rules: https://developers.cloudflare.com/r2/buckets/object-lifecycles/
