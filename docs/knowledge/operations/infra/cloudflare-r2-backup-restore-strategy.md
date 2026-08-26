# cloudflare-r2-backup-restore-strategy

**Issue:** Designing a backup and restore strategy for R2 buckets
         and D1 databases using Workers cron, object versioning,
         cross-bucket replication, and encrypted archive objects
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

A misconfigured lifecycle rule deletes objects from the primary
R2 bucket. A bad D1 migration drops a table. There is no backup
because "R2 is durable" was assumed to mean "R2 is recoverable".
Cloudflare's 11-nines durability protects against hardware loss,
not logical deletion. Versioning and explicit backup routines are
required to recover from application-layer errors.

## Context

R2 does not replicate objects to a second bucket automatically.
Object versioning (when enabled) keeps previous versions in the
same bucket but does not protect against bucket deletion or
account-level incidents. A robust strategy layers:
1. In-bucket versioning for instant rollback
2. Cross-bucket replication for geographic/account separation
3. D1 export to R2 on a schedule with encryption at rest
4. Verification cron to ensure backups are non-empty and decrytable

---

## Layer 1: In-Bucket Object Versioning

Versioning is enabled per bucket in the Cloudflare dashboard or
via the API. Once enabled, overwrite and delete operations create
new versions rather than destroying the previous version.

```bash
# Enable via API (no wrangler.toml support yet — use REST)
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID\
/r2/buckets/myapp-uploads/versioning" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"Status": "Enabled"}'
```

```
Versioning behaviour:
  PUT object  → creates new version, old version retained
  DELETE obj  → inserts "delete marker", old versions retained
  GET object  → returns current version (latest)
  GET object
    ?versionId=<id> → returns specific version
```

List versions from a Worker binding:

```ts
// List all versions of an object
const listed = await env.UPLOADS.list({
  prefix: "user-avatars/u_123",
  include: ["httpMetadata", "customMetadata"],
});

// Restore a specific version by copying it back
const old = await env.UPLOADS.get(
  "user-avatars/u_123.jpg",
  { onlyIf: { uploadId: "specific-version-id" } }
);
if (old) {
  await env.UPLOADS.put("user-avatars/u_123.jpg", old.body);
}
```

---

## Layer 2: Cross-Bucket Replication via Cron Worker

Replicate objects from the primary bucket to a backup bucket on
a scheduled Worker. The backup bucket should be in a separate
Cloudflare account when possible (protects against account-level
suspension or credential compromise).

```toml
# wrangler.toml — backup worker
name = "r2-replicator"
main = "src/replicator.ts"
compatibility_date = "2025-10-01"

[[r2_buckets]]
binding     = "SOURCE"
bucket_name = "myapp-uploads"

[[r2_buckets]]
binding     = "BACKUP"
bucket_name = "myapp-uploads-backup"

[triggers]
crons = ["0 2 * * *"]   # 02:00 UTC daily
```

```ts
// src/replicator.ts
interface Env {
  SOURCE: R2Bucket;
  BACKUP: R2Bucket;
  LAST_REPLICATED_KEY: KVNamespace;  // checkpoint
}

export default {
  async scheduled(_: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(replicate(env));
  },
};

async function replicate(env: Env): Promise<void> {
  const checkpoint = await env.LAST_REPLICATED_KEY.get("checkpoint");
  let cursor: string | undefined = checkpoint ?? undefined;
  let replicated = 0;

  do {
    const list = await env.SOURCE.list({
      cursor,
      limit: 1000,
    });

    for (const obj of list.objects) {
      const existing = await env.BACKUP.head(obj.key);
      // Skip if backup is up to date (same etag)
      if (existing?.etag === obj.etag) continue;

      const src = await env.SOURCE.get(obj.key);
      if (!src) continue;

      await env.BACKUP.put(obj.key, src.body, {
        httpMetadata:   src.httpMetadata,
        customMetadata: src.customMetadata,
      });
      replicated++;
    }

    cursor = list.truncated ? list.cursor : undefined;
    if (cursor) {
      await env.LAST_REPLICATED_KEY.put("checkpoint", cursor);
    }
  } while (cursor);

  // Clear checkpoint after full pass
  await env.LAST_REPLICATED_KEY.delete("checkpoint");
  console.log(`Replication complete. Objects synced: ${replicated}`);
}
```

---

## Layer 3: D1 Database Backup to R2

D1 does not currently expose native backup-to-external-storage.
Use D1 Time Travel (built-in, last 30 days) for point-in-time
recovery within the platform, and export snapshots to R2 for
longer retention or offline archival.

```bash
# Export D1 to SQL file (run in CI or local with wrangler)
wrangler d1 export myapp-production \
  --output ./backup-$(date +%Y%m%d).sql

# Encrypt before storing (AES-256-CBC via openssl)
openssl enc -aes-256-cbc -salt \
  -in  ./backup-20260822.sql \
  -out ./backup-20260822.sql.enc \
  -k   "$BACKUP_ENCRYPTION_KEY"

# Upload encrypted file to R2 via wrangler
wrangler r2 object put \
  myapp-backups/d1/myapp-production/20260822.sql.enc \
  --file ./backup-20260822.sql.enc
```

For automated nightly backups via cron Worker (requires Wrangler
in a child process or `D1.dump()` — which is available in
Workers SDK as of 2026-Q1):

```ts
// Dump all tables to a JSON snapshot
async function backupD1(
  env: Env, ctx: ExecutionContext
): Promise<void> {
  const tables = await env.DB.prepare(
    "SELECT name FROM sqlite_master WHERE type='table'"
  ).all<{ name: string }>();

  const snapshot: Record<string, unknown[]> = {};
  for (const { name } of tables.results) {
    const rows = await env.DB.prepare(
      `SELECT * FROM "${name}"`
    ).all();
    snapshot[name] = rows.results;
  }

  const json  = JSON.stringify(snapshot);
  const key   = new TextEncoder().encode(env.BACKUP_KEY);
  // Workers SubtleCrypto — AES-GCM encryption
  const iv    = crypto.getRandomValues(new Uint8Array(12));
  const ck    = await crypto.subtle.importKey(
    "raw", key, { name: "AES-GCM" }, false, ["encrypt"]
  );
  const ct    = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv }, ck, new TextEncoder().encode(json)
  );

  const date  = new Date().toISOString().slice(0, 10);
  const r2key = `d1-snapshots/${date}.json.enc`;

  // Prefix iv to ciphertext for restore
  const buf = new Uint8Array(iv.byteLength + ct.byteLength);
  buf.set(iv, 0);
  buf.set(new Uint8Array(ct), iv.byteLength);

  await env.BACKUPS.put(r2key, buf, {
    customMetadata: { tables: tables.results.length.toString() }
  });
}
```

---

## Layer 4: Backup Verification Cron

A separate verification Worker runs after the backup cron and
confirms the backup object is readable and decryptable:

```ts
export default {
  async scheduled(_: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const date   = new Date().toISOString().slice(0, 10);
    const r2key  = `d1-snapshots/${date}.json.enc`;
    const obj    = await env.BACKUPS.get(r2key);

    if (!obj) {
      await sendAlert(env, `BACKUP MISSING: ${r2key}`);
      return;
    }

    const size = obj.size;
    if (size < 1024) {
      await sendAlert(env, `BACKUP TOO SMALL: ${r2key} (${size}b)`);
      return;
    }

    // Attempt decrypt (AES-GCM)
    try {
      const buf  = await obj.arrayBuffer();
      const iv   = buf.slice(0, 12);
      const ct   = buf.slice(12);
      const key  = await crypto.subtle.importKey(
        "raw", new TextEncoder().encode(env.BACKUP_KEY),
        { name: "AES-GCM" }, false, ["decrypt"]
      );
      const pt   = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: new Uint8Array(iv) }, key, ct
      );
      const json = new TextDecoder().decode(pt);
      JSON.parse(json); // throws if malformed
    } catch (e) {
      await sendAlert(env, `BACKUP DECRYPT FAILED: ${r2key}: ${e}`);
    }
  },
};
```

---

## Restore Procedure

```
Restore from cross-bucket backup (R2 objects):
  1. Identify the date of last known-good state
  2. List objects in backup bucket for that date
  3. Copy objects back to primary bucket via Worker or wrangler:
     wrangler r2 object get myapp-uploads-backup/<key> --file /tmp/obj
     wrangler r2 object put myapp-uploads/<key> --file /tmp/obj

Restore D1 from R2 snapshot:
  1. Download encrypted backup:
     wrangler r2 object get myapp-backups/d1/production/20260822.sql.enc \
       --file ./backup.sql.enc
  2. Decrypt:
     openssl enc -d -aes-256-cbc -in backup.sql.enc \
       -out backup.sql -k "$BACKUP_ENCRYPTION_KEY"
  3. Import to a new (or reset) D1 database:
     wrangler d1 execute myapp-restore --file ./backup.sql
  4. Verify row counts match pre-incident metrics

Restore D1 via Time Travel (within 30-day window):
  wrangler d1 time-travel restore myapp-production \
    --timestamp "2026-08-21T18:00:00Z"
```

---

## Anti-patterns

- **Treating R2 durability as recoverability.** Durability means
  hardware redundancy; it does not protect against a DELETE call
  from your own Worker. Enable versioning.
- **Storing the encryption key in `[vars]`.** Anyone with repo
  access can read the backups. Store it as a `wrangler secret`.
- **Not verifying backups.** Write-only backup crons frequently
  fail silently for months. Verification is not optional.
- **Replicating into the same Cloudflare account.** An account
  suspension or credential leak affects both buckets. Keep the
  backup bucket in a separate account or push to external storage.

## Gotchas

- D1 Time Travel snapshots are only available for 30 days. Beyond
  30 days, R2-based snapshots are the only recovery path.
- Versioning incurs storage cost for every retained version.
  Configure an R2 lifecycle rule to expire non-current versions
  after N days to control cost.
- The Workers KV checkpoint pattern for replication restarts from
  the cursor on failure. If the replicator Worker is killed mid-
  run, the next cron picks up from the stored cursor. Test this
  recovery path explicitly.
- AES-GCM nonces (IVs) must be unique per encryption. The
  `crypto.getRandomValues()` approach above is correct; do not
  reuse IVs or switch to a counter-based scheme without careful
  analysis.

## Verification

- **Replication:** `wrangler r2 object list myapp-uploads-backup`
  → object count matches primary within 24 h
- **D1 backup:** Check R2 for today's `.json.enc` object with
  `wrangler r2 object list myapp-backups/d1/production/`
- **Alert:** `sendAlert` should reach your oncall channel within
  5 min of a backup failure
- **Restore drill:** Quarterly — restore last week's backup to a
  test D1 database, verify row counts match production snapshot

## Related

- `cloudflare/r2-best-practices.md`
- `cloudflare/r2-lifecycle-rules.md`
- `cloudflare/d1-time-travel.md`
- `cloudflare/d1-export-import.md`
- `infra/backup-verification-3-2-1.md`

## Source URLs

- https://developers.cloudflare.com/r2/buckets/object-versioning/
- https://developers.cloudflare.com/d1/reference/time-travel/
- https://developers.cloudflare.com/r2/api/workers/
- https://developers.cloudflare.com/d1/platform/export-import/
