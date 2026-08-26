# AWS S3 to Cloudflare R2 Migration with Terraform

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**: You are paying significant AWS S3 egress fees and want to migrate object storage to Cloudflare R2, which charges zero egress. The migration must be zero-downtime, keep both stores in sync during a dual-write window, validate object parity, and cut over readers without a deployment outage.

**Context**: R2 is S3-API-compatible, so most SDKs switch with a config change. The migration strategy is: (1) provision R2 bucket via Terraform alongside existing S3 buckets, (2) backfill objects using `rclone` or a Workers migration script, (3) enable dual-write in the application layer, (4) validate parity, (5) cut over readers, (6) drain S3 writes and decommission. Terraform manages both sides declaratively; the migration Worker handles backfill and live mirroring.

---

## Terraform: Provision R2 Alongside S3

```hcl
# terraform/r2-migration.tf

terraform {
  required_providers {
    cloudflare = { source = "cloudflare/cloudflare" version = "~> 4.0" }
    aws        = { source = "hashicorp/aws"          version = "~> 5.0" }
  }
}

# Existing S3 bucket (read-only reference, not managed here)
data "aws_s3_bucket" "source" {
  bucket = var.s3_source_bucket
}

# New R2 bucket matching the S3 bucket name (or aliased)
resource "cloudflare_r2_bucket" "destination" {
  account_id = var.cloudflare_account_id
  name       = var.r2_bucket_name
  location   = "ENAM"  # Eastern North America — closest to us-east-1
}

# R2 custom domain for zero-egress public access
resource "cloudflare_r2_bucket" "destination_public" {
  account_id = var.cloudflare_account_id
  name       = var.r2_bucket_name
  location   = "ENAM"

  lifecycle { prevent_destroy = true }
}

# CORS policy matching S3 bucket's existing CORS config
resource "cloudflare_r2_bucket_cors" "destination" {
  account_id = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.destination.name

  rules = [
    {
      allowed_origins = var.cors_origins
      allowed_methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
      allowed_headers = ["*"]
      expose_headers  = ["ETag", "Content-Length", "Content-Type"]
      max_age_seconds = 3600
    }
  ]
}

# R2 API token for application access (least privilege)
resource "cloudflare_api_token" "r2_readwrite" {
  name = "r2-${var.r2_bucket_name}-readwrite"

  policy {
    permission_groups = [
      data.cloudflare_api_token_permission_groups.all.object_read_write["Workers R2 Storage Write"],
    ]
    resources = {
      "com.cloudflare.edge.r2.bucket.${var.cloudflare_account_id}_default_${var.r2_bucket_name}" = "*"
    }
  }
}

output "r2_endpoint" {
  value = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com"
}

output "r2_bucket_name" {
  value = cloudflare_r2_bucket.destination.name
}
```

## Backfill: rclone Configuration

```bash
# ~/.config/rclone/rclone.conf
[s3-source]
type = s3
provider = AWS
env_auth = true
region = us-east-1

[r2-dest]
type = s3
provider = Cloudflare
access_key_id     = <r2-access-key-id>
secret_access_key = <r2-secret-access-key>
endpoint          = https://<account-id>.r2.cloudflarestorage.com
acl               = private

# Run backfill with checksum verification (--checksum uses ETag/MD5)
# --transfers 32: parallel transfers; R2 handles high concurrency well
rclone sync s3-source:<bucket> r2-dest:<r2-bucket> \
  --checksum \
  --transfers 32 \
  --s3-chunk-size 64M \
  --progress \
  --log-file=backfill.log \
  --log-level INFO

# After initial sync, run again to pick up delta changes
rclone sync s3-source:<bucket> r2-dest:<r2-bucket> \
  --checksum --transfers 16 --progress
```

## Dual-Write Workers Middleware Pattern

```typescript
// dual-write-proxy/src/index.ts
// Routes all writes to both S3 and R2 during migration window

export interface Env {
  S3_BUCKET_URL: string;       // https://s3.amazonaws.com/<bucket>
  R2_BUCKET: R2Bucket;         // Direct R2 binding
  DUAL_WRITE_ENABLED: string;  // "true" during migration, "false" after
  READ_FROM: string;            // "s3" | "r2" | "both-verify"
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading /

    if (request.method === "GET" || request.method === "HEAD") {
      return handleRead(key, request.method, env);
    }
    if (request.method === "PUT" || request.method === "POST") {
      return handleWrite(key, request, env);
    }
    if (request.method === "DELETE") {
      return handleDelete(key, env);
    }
    return new Response("Method Not Allowed", { status: 405 });
  },
};

async function handleRead(key: string, method: string, env: Env): Promise<Response> {
  if (env.READ_FROM === "r2") {
    const obj = method === "HEAD"
      ? await env.R2_BUCKET.head(key)
      : await env.R2_BUCKET.get(key);
    if (!obj) return new Response("Not Found", { status: 404 });
    const headers = new Headers();
    if ("httpMetadata" in obj && obj.httpMetadata?.contentType) {
      headers.set("Content-Type", obj.httpMetadata.contentType);
    }
    if ("etag" in obj) headers.set("ETag", obj.etag);
    return method === "HEAD"
      ? new Response(null, { headers })
      : new Response((obj as R2ObjectBody).body, { headers });
  }
  // Default: proxy to S3
  return fetch(`${env.S3_BUCKET_URL}/${key}`, { method });
}

async function handleWrite(key: string, request: Request, env: Env): Promise<Response> {
  const body = await request.arrayBuffer();
  const contentType = request.headers.get("Content-Type") ?? "application/octet-stream";

  if (env.DUAL_WRITE_ENABLED === "true") {
    // Write to both in parallel; fail if either fails
    const [s3Res] = await Promise.all([
      fetch(`${env.S3_BUCKET_URL}/${key}`, {
        method: "PUT",
        body,
        headers: { "Content-Type": contentType },
      }),
      env.R2_BUCKET.put(key, body, { httpMetadata: { contentType } }),
    ]);
    return new Response(null, { status: s3Res.status });
  }

  // After cutover: write only to R2
  await env.R2_BUCKET.put(key, body, { httpMetadata: { contentType } });
  return new Response(null, { status: 200 });
}

async function handleDelete(key: string, env: Env): Promise<Response> {
  if (env.DUAL_WRITE_ENABLED === "true") {
    await Promise.all([
      fetch(`${env.S3_BUCKET_URL}/${key}`, { method: "DELETE" }),
      env.R2_BUCKET.delete(key),
    ]);
  } else {
    await env.R2_BUCKET.delete(key);
  }
  return new Response(null, { status: 204 });
}
```

## Parity Validation Script

```typescript
// validate-parity/src/index.ts — run as a one-off Worker or local script
// Compares ETags between S3 and R2 to confirm objects match

interface PairResult { key: string; match: boolean; s3Etag?: string; r2Etag?: string }

export interface Env { R2_BUCKET: R2Bucket; S3_LIST_URL: string; }

export default {
  async fetch(_: Request, env: Env): Promise<Response> {
    const mismatches: PairResult[] = [];
    let cursor: string | undefined;

    do {
      const listed = await env.R2_BUCKET.list({ cursor, limit: 1000 });
      const checks = listed.objects.map(async (obj) => {
        const s3Head = await fetch(`${env.S3_LIST_URL}/${obj.key}`, { method: "HEAD" });
        const s3Etag = s3Head.headers.get("etag")?.replace(/"/g, "");
        const r2Etag = obj.etag;
        const match = s3Etag === r2Etag;
        if (!match) mismatches.push({ key: obj.key, match, s3Etag, r2Etag });
      });
      await Promise.all(checks);
      cursor = listed.truncated ? listed.cursor : undefined;
    } while (cursor);

    return Response.json({ mismatches, total_mismatches: mismatches.length });
  },
};
```

## Cutover Terraform Variables

```hcl
# terraform/migration-phase.tfvars

# Phase 1: Backfill running, dual-write not yet enabled
dual_write_enabled = false
read_from          = "s3"

# Phase 2: Dual-write active, reads still from S3
# dual_write_enabled = true
# read_from          = "s3"

# Phase 3: Dual-write active, reads from R2
# dual_write_enabled = true
# read_from          = "r2"

# Phase 4: Migration complete — R2 only
# dual_write_enabled = false
# read_from          = "r2"
```

---

**Anti-patterns**:
- Cutting reads to R2 before the backfill completes — objects written to S3 before dual-write started are missing in R2.
- Using `rclone copy` instead of `rclone sync` for the backfill — `copy` does not delete objects removed from S3; `sync` maintains parity.
- Ignoring multipart upload differences — S3 ETags for multipart uploads are composite hashes that differ from R2's ETags; validate with content hash, not ETag, for large objects.
- Storing AWS and R2 credentials in the same secret — use separate IAM roles and R2 API tokens with minimum required permissions.
- Not setting R2 `location` to match the S3 region — routing mismatches add latency during the dual-write window.

**Gotchas**:
- R2 does not support S3 Object Lock or WORM compliance features as of 2026 — if S3 compliance retention is in use, R2 is not a drop-in replacement without compensating controls.
- S3 presigned URL signatures are not compatible with R2; regenerate presigned URLs using R2's S3-compatible endpoint after cutover.
- R2 does not emit S3-compatible event notifications — migrate any S3 event → Lambda → SQS pipelines to R2 event notifications → Workers before decommissioning S3.
- `rclone sync` deletes objects in the destination that are not in the source — double-check flags when syncing incrementally to avoid accidental R2 deletions.
- The Cloudflare R2 API rate limit is per-account, not per-bucket; a high-throughput backfill can starve other R2 operations in the same account.

**Verification**:
```bash
# Compare object counts between S3 and R2
aws s3 ls s3://<bucket>/ --recursive | wc -l
rclone ls r2-dest:<r2-bucket> | wc -l

# Run parity check on a sample (1000 objects)
rclone check s3-source:<bucket> r2-dest:<r2-bucket> \
  --checksum --max-depth 1 --log-level INFO

# After cutover: confirm S3 is receiving no new writes
aws s3api list-object-versions --bucket <bucket> \
  --query "Versions[?LastModified>='2026-08-23'].Key" --output text
```

**Related**:
- `cloudflare-r2-backup-restore-strategy.md`
- `r2-lifecycle-archival-glacier-strategy.md`
- `object-storage-replication.md`
- `aws-s3-lifecycle-policies.md`
- `pulumi-cloudflare-r2-cors-policy.md`

**Sources**:
- https://developers.cloudflare.com/r2/api/s3/api/
- https://rclone.org/cloudflare/
- https://developers.cloudflare.com/r2/buckets/cors/
- https://developers.cloudflare.com/r2/migrating/
