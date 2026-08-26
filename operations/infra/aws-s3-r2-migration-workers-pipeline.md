# Migrating Data from AWS S3 to Cloudflare R2 Using a Workers Pipeline

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to move objects from an AWS S3 bucket to Cloudflare R2 without downtime, with progress tracking and ETag-based validation to ensure byte-perfect copies.

## Context

Two approaches exist:

| Approach | Pros | Cons |
|---|---|---|
| `rclone copy s3:bucket r2:bucket` | Simple, single command | Runs from a machine with both credentials; not resumable natively; no per-object audit |
| Workers cron pipeline | Runs inside Cloudflare; resumable; per-object D1 log; validates ETag | More setup; 30 s CPU limit per invocation |

This article covers the Workers pipeline. Use `rclone` for one-shot migrations under 50 k objects; use the Workers pipeline for large datasets, incremental syncs, or when you need an audit log.

Prerequisites:
- R2 bucket bound to the Worker as `R2`
- D1 database bound as `DB`
- AWS credentials stored as Worker Secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- `wrangler` >= 3.50

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS migration_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  s3_key      TEXT    NOT NULL UNIQUE,
  r2_key      TEXT    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'pending',  -- pending | copied | failed | validated
  s3_etag     TEXT,
  r2_etag     TEXT,
  size_bytes  INTEGER,
  copied_at   TEXT,
  error       TEXT
);

CREATE INDEX idx_migration_log_status ON migration_log(status);
```

---

## Worker: S3 → R2 Pipeline with Presigned URL Auth

```typescript
// src/index.ts
import { AwsClient } from 'aws4fetch';

export interface Env {
  R2:                   R2Bucket;
  DB:                   D1Database;
  AWS_ACCESS_KEY_ID:    string;
  AWS_SECRET_ACCESS_KEY: string;
  AWS_REGION:           string;
  S3_BUCKET:            string;
  BATCH_SIZE:           string;   // default '100'
}

const BATCH = (env: Env) => parseInt(env.BATCH_SIZE ?? '100', 10);

async function presignedGet(aws: AwsClient, bucket: string, region: string, key: string): Promise<string> {
  const url = `https://${bucket}.s3.${region}.amazonaws.com/${encodeURIComponent(key)}`;
  const signed = await aws.sign(new Request(url), { aws: { signQuery: true } });
  return signed.url.toString();
}

async function copyObject(aws: AwsClient, env: Env, s3Key: string): Promise<void> {
  const signedUrl = await presignedGet(aws, env.S3_BUCKET, env.AWS_REGION, s3Key);

  // Fetch from S3 via presigned URL — no S3 credentials exposed to R2
  const s3Resp = await fetch(signedUrl);
  if (!s3Resp.ok) throw new Error(`S3 fetch failed: ${s3Resp.status} ${s3Key}`);

  const s3Etag    = s3Resp.headers.get('etag') ?? '';
  const sizeBytes = parseInt(s3Resp.headers.get('content-length') ?? '0', 10);
  const body      = await s3Resp.arrayBuffer();

  // Write to R2
  const r2Obj = await env.R2.put(s3Key, body, {
    httpMetadata: { contentType: s3Resp.headers.get('content-type') ?? 'application/octet-stream' },
    customMetadata: { s3_etag: s3Etag },
  });

  await env.DB.prepare(
    `UPDATE migration_log
     SET status='copied', s3_etag=?, r2_etag=?, size_bytes=?, copied_at=datetime('now')
     WHERE s3_key=?`
  ).bind(s3Etag, r2Obj.etag, sizeBytes, s3Key).run();
}

async function validateObject(env: Env, s3Key: string): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT s3_etag, r2_etag FROM migration_log WHERE s3_key=?`
  ).bind(s3Key).all<{ s3_etag: string; r2_etag: string }>();

  if (!results.length) throw new Error(`No migration record for ${s3Key}`);
  const { s3_etag, r2_etag } = results[0];

  // R2 ETag wraps value in quotes; S3 may or may not
  const normalise = (e: string) => e.replace(/"/g, '').toLowerCase();
  if (normalise(s3_etag) !== normalise(r2_etag)) {
    await env.DB.prepare(`UPDATE migration_log SET status='failed', error=? WHERE s3_key=?`)
      .bind(`ETag mismatch: s3=${s3_etag} r2=${r2_etag}`, s3Key).run();
    throw new Error(`ETag mismatch for ${s3Key}`);
  }

  await env.DB.prepare(`UPDATE migration_log SET status='validated' WHERE s3_key=?`)
    .bind(s3Key).run();
}

export default {
  // Cron trigger: processes one batch of pending objects per invocation
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const aws = new AwsClient({
      accessKeyId:     env.AWS_ACCESS_KEY_ID,
      secretAccessKey: env.AWS_SECRET_ACCESS_KEY,
      region:          env.AWS_REGION,
      service:         's3',
    });

    const { results } = await env.DB.prepare(
      `SELECT s3_key FROM migration_log WHERE status='pending' LIMIT ?`
    ).bind(BATCH(env)).all<{ s3_key: string }>();

    console.log(`[migration] Processing ${results.length} objects`);

    await Promise.allSettled(
      results.map(async ({ s3_key }) => {
        try {
          await copyObject(aws, env, s3Key);
          await validateObject(env, s3_key);
        } catch (err) {
          console.error(`[migration] Failed ${s3_key}:`, err);
          await env.DB.prepare(`UPDATE migration_log SET status='failed', error=? WHERE s3_key=?`)
            .bind(String(err), s3_key).run();
        }
      })
    );
  },
};
```

---

## wrangler.toml

```toml
name = "s3-r2-migration"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding  = "DB"
database_name = "migration-audit"
database_id   = "<your-d1-id>"

[[r2_buckets]]
binding     = "R2"
bucket_name = "my-r2-bucket"

[triggers]
crons = ["*/5 * * * *"]  # every 5 minutes during active migration

[vars]
AWS_REGION  = "us-east-1"
S3_BUCKET   = "my-legacy-bucket"
BATCH_SIZE  = "100"
```

---

## Seeding the Migration Log from S3

```bash
# List all S3 keys and insert as 'pending' into D1
aws s3api list-objects-v2 --bucket my-legacy-bucket --query 'Contents[].Key' --output text \
  | tr '\t' '\n' \
  | jq -Rs 'split("\n") | map(select(length>0)) | map({s3_key:., r2_key:.})' \
  > objects.json

# Batch-insert via D1 REST API (pseudo-script; chunk into 100-row batches)
python3 seed_migration.py objects.json
```

---

## rclone Approach (Quick Reference)

```bash
# Configure rclone with both providers, then:
rclone copy s3:my-legacy-bucket r2:my-r2-bucket \
  --transfers 32 \
  --checkers 16 \
  --s3-chunk-size 64M \
  --progress

# Verify counts match
rclone check s3:my-legacy-bucket r2:my-r2-bucket --one-way
```

---

## Anti-patterns

- **Fetching large objects into Worker memory**: Workers have a 128 MB memory limit. Stream large objects in chunks or use a signed URL redirect for objects > 50 MB.
- **Using S3 SDK directly in Workers**: the full AWS SDK is too large for Workers. Use `aws4fetch` (presigned URLs) instead.
- **Ignoring multipart ETags**: S3 multipart upload ETags are `md5-of-parts-N`; they will not match an R2 ETag. Track these separately and validate by re-downloading and hashing.
- **Running all objects in one cron**: the 30 s CPU limit means batches of ~100 objects are safe for typical object sizes.

## Gotchas

- R2 `put()` returns an `R2Object` with `.etag`; this ETag is a standard MD5 for single-part puts but differs for multipart uploads.
- D1 `UNIQUE` constraint on `s3_key` prevents duplicate inserts if the seed script is run twice.
- Worker Secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) do not appear in `wrangler.toml` — add them with `wrangler secret put`.

## Verification

```sql
-- Migration progress dashboard
SELECT status, COUNT(*) AS cnt, SUM(size_bytes)/1e9 AS gb
FROM migration_log
GROUP BY status;

-- Failed objects for retry
SELECT s3_key, error FROM migration_log WHERE status='failed';
```

```bash
# Reset failed objects for retry
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"sql":"UPDATE migration_log SET status=\'pending\', error=NULL WHERE status=\'failed\'"}'
```

## Related

- `terraform-workers-secret-rotation-automation.md`
- `cloudflare-r2-lifecycle-rules.md`
- `cloudflare-workers-cron-patterns.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/d1/
- https://github.com/mhart/aws4fetch
- https://developers.cloudflare.com/workers/runtime-apis/bindings/r2/
