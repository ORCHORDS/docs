# Cloudflare R2 Super Slurper: Bulk Cloud Storage Migration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to migrate a large bucket — tens of thousands to hundreds of millions of
objects — from Amazon S3, Google Cloud Storage (GCS), or another S3-compatible store
into Cloudflare R2. Copying objects manually with `aws s3 sync` or custom scripts is
slow, brittle at scale, requires running a machine for days, and does not handle
incremental syncs cleanly. You want a managed, Cloudflare-side pull-copy that runs
entirely within Cloudflare's network without routing data through your own servers.

## Context

**R2 Super Slurper** is a Cloudflare-managed migration service that pulls objects from
a source bucket into a target R2 bucket. As of 2026 it supports:

- **Sources**: AWS S3, GCS (via S3-interop), any S3-compatible endpoint (Backblaze B2,
  Wasabi, MinIO with public endpoint)
- **Operation**: parallel pull-copy from within Cloudflare's network; objects are
  streamed directly from source to R2 — your egress costs apply only at the source
- **Incremental sync**: re-running a migration job skips objects that already exist in
  R2 with a matching ETag (no re-copy of unchanged objects)
- **Object metadata**: content-type, user-defined metadata, and cache-control are
  preserved; server-side encryption keys from AWS KMS must be handled separately
- **Pricing**: Cloudflare bills R2 Class A write operations per object copied; no
  additional Super Slurper fee

Super Slurper is configured via the Cloudflare Dashboard (Storage → R2 → Migrate) or
via the Cloudflare API. It does not require any Cloudflare Workers or wrangler.toml.

## Preparing the Source Bucket

### AWS S3

Create a dedicated read-only IAM user or role for Super Slurper:

```json
// iam-policy-super-slurper-s3.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SuperSlurperRead",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectTagging",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::my-source-bucket",
        "arn:aws:s3:::my-source-bucket/*"
      ]
    }
  ]
}
```

```bash
# Create IAM user
aws iam create-user --user-name cf-super-slurper

# Attach inline policy
aws iam put-user-policy \
  --user-name cf-super-slurper \
  --policy-name R2MigrationReadOnly \
  --policy-document file://iam-policy-super-slurper-s3.json

# Generate access key
aws iam create-access-key --user-name cf-super-slurper
# Save the AccessKeyId and SecretAccessKey — these go into Super Slurper config
```

### Google Cloud Storage (via S3 Interoperability)

GCS exposes an S3-compatible API that Super Slurper can target:

```bash
# In GCP Console → Cloud Storage → Settings → Interoperability
# Create an HMAC key for the service account that owns the bucket
# Note the Access Key and Secret
BUCKET_REGION="us-east1"   # use the nearest equivalent
S3_ENDPOINT="https://storage.googleapis.com"
```

## Creating the Migration Job via API

The Cloudflare API approach is useful for scripting and CI/CD-triggered migrations:

```typescript
// scripts/start-migration.ts
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;  // needs Workers R2:Edit

interface SuperSlurperJobRequest {
  source: {
    provider: 'aws_s3' | 'gcs';
    region: string;
    bucket: string;
    prefix?: string;
    access_key_id: string;
    secret_access_key: string;
    endpoint?: string;   // for S3-compatible non-AWS endpoints
  };
  target: {
    bucket: string;   // R2 bucket name
  };
  overwrite_if_exists: boolean;
}

async function createMigrationJob(opts: SuperSlurperJobRequest): Promise<string> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/slurper/jobs`;

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(opts),
  });

  if (!resp.ok) {
    throw new Error(`Job creation failed: ${resp.status} ${await resp.text()}`);
  }

  const data = await resp.json() as { result: { id: string } };
  return data.result.id;
}

async function pollJob(jobId: string): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/slurper/jobs/${jobId}`;

  while (true) {
    const resp = await fetch(url, {
      headers: { 'Authorization': `Bearer ${API_TOKEN}` },
    });
    const data = await resp.json() as {
      result: {
        status: 'running' | 'complete' | 'error' | 'paused';
        stats: { objects_copied: number; objects_skipped: number; bytes_copied: number };
        error?: string;
      };
    };

    const { status, stats, error } = data.result;
    console.log(`[${new Date().toISOString()}] status=${status}`, stats);

    if (status === 'complete') {
      console.log('Migration complete:', stats);
      break;
    }
    if (status === 'error') {
      throw new Error(`Migration failed: ${error}`);
    }

    await new Promise(r => setTimeout(r, 30_000)); // poll every 30 s
  }
}

// Example usage
(async () => {
  const jobId = await createMigrationJob({
    source: {
      provider: 'aws_s3',
      region: 'us-east-1',
      bucket: 'my-source-bucket',
      prefix: 'media/',             // migrate only objects under media/
      access_key_id: process.env.AWS_ACCESS_KEY_ID!,
      secret_access_key: process.env.AWS_SECRET_ACCESS_KEY!,
    },
    target: {
      bucket: 'my-r2-target-bucket',
    },
    overwrite_if_exists: false,    // skip already-copied objects
  });

  console.log(`Migration job created: ${jobId}`);
  await pollJob(jobId);
})();
```

## Incremental Sync Strategy

Super Slurper does a **list-then-copy** pass. Objects already in R2 with an identical
ETag are skipped. For a live migration (source still receiving writes), run the job in
multiple passes:

```bash
# Pass 1 — bulk copy (runs for hours/days on large buckets)
# Pass 2 — incremental sync of newly written objects
# Cutover — update DNS / application config to point at R2
# Pass 3 (optional) — final delta run to catch any tail writes

# Monitor via API or Dashboard progress panel
```

For zero-downtime cutovers, combine Super Slurper with a Workers-based migration proxy
that falls back to the source during the window:

```typescript
// src/migration-proxy.ts — deploy in front of R2 custom domain during cutover
export interface Env {
  R2_BUCKET: R2Bucket;
  SOURCE_BUCKET_URL: string; // e.g. https://s3.amazonaws.com/my-source-bucket
  SOURCE_READ_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const key = new URL(request.url).pathname.slice(1); // strip leading /

    // Try R2 first
    const r2Obj = await env.R2_BUCKET.get(key);
    if (r2Obj) {
      return new Response(r2Obj.body, {
        headers: {
          'Content-Type': r2Obj.httpMetadata?.contentType ?? 'application/octet-stream',
          'ETag': r2Obj.httpEtag,
          'Last-Modified': r2Obj.uploaded.toUTCString(),
          'X-Source': 'r2',
        },
      });
    }

    // Fall back to source
    const sourceResp = await fetch(`${env.SOURCE_BUCKET_URL}/${key}`, {
      headers: { Authorization: `Bearer ${env.SOURCE_READ_TOKEN}` },
    });

    if (!sourceResp.ok) return new Response('Not found', { status: 404 });

    // Warm R2 asynchronously (fire-and-forget write behind)
    // Note: body can only be consumed once — clone before consuming
    const [forResponse, forWrite] = sourceResp.body!.tee();

    void (async () => {
      try {
        await env.R2_BUCKET.put(key, forWrite, {
          httpMetadata: { contentType: sourceResp.headers.get('content-type') ?? undefined },
        });
      } catch { /* non-critical */ }
    })();

    return new Response(forResponse, {
      status: 200,
      headers: {
        'Content-Type': sourceResp.headers.get('content-type') ?? 'application/octet-stream',
        'X-Source': 'origin-fallback',
      },
    });
  },
};
```

## Anti-patterns

- **Using `overwrite_if_exists: true` on a live production bucket** — This forces a
  re-copy of every object, burning Class A operations and bandwidth. Use `false` after
  the initial pass.
- **Migrating with object-level ACLs** — R2 does not have per-object ACLs. If your S3
  bucket uses per-object `public-read` ACLs, evaluate whether R2 bucket-level public
  access or signed URLs fit your access model before migrating.
- **Relying on S3 `LastModified` for delta detection** — Super Slurper uses ETag
  matching. If your source bucket rewrites objects without changing their content (same
  bytes, new `LastModified`), Super Slurper will skip them correctly. If ETag algorithms
  differ (multipart upload ETags are composite), verify with a spot-check.
- **Starting migration on terabyte-scale buckets without a prefix filter** — Scope the
  first run with a `prefix` to validate the pipeline before running the full migration.

## Gotchas

- **Multipart upload ETags on S3** — Objects uploaded to S3 with multipart upload have
  ETags of the form `"<hash>-<partcount>"`. R2 also stores multipart ETags but the
  hash is computed differently. Super Slurper stores the S3 ETag as-is in R2's metadata
  field, so ETag comparison for subsequent incremental syncs works correctly within
  Super Slurper. External clients comparing ETags between S3 and R2 may see mismatches.
- **AWS KMS-encrypted objects (SSE-KMS)** — Super Slurper cannot decrypt SSE-KMS
  objects (only SSE-S3 and SSE-C are accessible without KMS). You must either re-encrypt
  to SSE-S3 before migrating, or copy those objects manually via a machine in-region.
- **R2 free tier vs. paid tier** — Super Slurper writes are Class A operations
  (`$4.50/million`). A 10-million-object bucket costs ~$45 in write ops. Factor this
  into egress cost comparisons with S3.
- **Source bucket in `ap-southeast-1` vs. Cloudflare PoP** — Super Slurper routes
  through Cloudflare edge; cross-region egress from the source still applies. Use an
  S3 bucket policy to allow Cloudflare IP ranges only if you want to limit pull access.
- **Migration job timeout** — Very large buckets (>100 M objects) can run for days.
  Jobs do not expire mid-run; monitor via Dashboard or API and re-trigger if a network
  hiccup causes an unexpected `error` status.

## Verification

```bash
# After migration, compare object counts
# Source (S3)
aws s3 ls s3://my-source-bucket --recursive | wc -l

# Target (R2 via wrangler)
wrangler r2 object list my-r2-target-bucket | jq '.objects | length'

# Spot-check a specific object's ETag
aws s3api head-object --bucket my-source-bucket --key media/sample.mp4 \
  | jq '.ETag'

curl -I https://pub-<r2-account-id>.r2.dev/media/sample.mp4 \
  | grep -i etag

# Verify content type preserved
curl -sI https://pub-<r2-account-id>.r2.dev/media/sample.mp4 \
  | grep -i content-type
```

Expected: object counts match (within expected delta from writes during migration
window), ETags match for S3-SSE objects, content types are preserved.

## Related

- `r2-best-practices.md` — R2 setup and configuration overview
- `r2-lifecycle-rules.md` — post-migration cleanup rules
- `r2-large-file-patterns.md` — handling multipart uploads
- `r2-cors-config.md` — configuring CORS after migration
- `cloudflare-r2-object-lifecycle-multipart.md` — lifecycle and multipart edge cases
- `r2-custom-domains-cache-rules.md` — serving migrated content via custom domain

## Sources

- R2 Super Slurper docs: https://developers.cloudflare.com/r2/data-migration/super-slurper/
- R2 pricing: https://developers.cloudflare.com/r2/pricing/
- R2 migration guide: https://developers.cloudflare.com/r2/data-migration/
- AWS S3 IAM best practices: https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html
- GCS S3 Interoperability: https://cloud.google.com/storage/docs/interoperability
