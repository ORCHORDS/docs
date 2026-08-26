# Cloudflare R2 Presigned URLs with Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your application needs to allow browser clients or mobile apps to upload files directly to R2 without
routing the binary payload through a Worker. Routing multi-megabyte uploads through a Worker consumes
CPU time, counts against the 100 MB request size limit, and adds latency. Presigned URLs let the
client PUT directly to R2's S3-compatible API endpoint, while your Worker controls authorization,
validates metadata, and scopes the upload to the correct key and expiry window.

## Context

R2 exposes an S3-compatible API at `https://<account-id>.r2.cloudflarestorage.com`. AWS Signature
Version 4 (SigV4) presigned URLs work against this endpoint. Cloudflare provides an `aws4fetch`
compatible helper; alternatively the Worker generates a `presignedUrl` using the `@aws-sdk/s3-request-presigner`
compiled for the edge, or using raw SigV4 signing via Web Crypto.

The lightest-weight production approach is `aws4fetch` + the R2 API token. The Worker signs the URL
server-side, returns it to the client, and the client uploads directly. The Worker never touches the
object bytes.

Key decisions:
- Expiry: presigned URLs should expire in 60–900 seconds; longer windows increase abuse risk.
- Key scoping: generate a deterministic key (e.g., `uploads/<user-id>/<uuid>.<ext>`) to prevent
  path traversal.
- Content-Type and Content-Length constraints can be embedded in the SigV4 signature so the client
  cannot upload an unexpected file type.
- Post-upload confirmation: use an R2 event notification → Queue → Worker or a separate
  `GET /upload/confirm` endpoint to move the object from a staging prefix to the final prefix after
  validation.

## Generating a Presigned PUT URL in a Worker

```typescript
// src/lib/r2-presign.ts
import { AwsClient } from "aws4fetch";  // bundled via npm

export interface PresignConfig {
  accountId:       string;
  accessKeyId:     string;
  secretAccessKey: string;
  bucket:          string;
  expiresIn:       number;  // seconds, max 604800 (7 days)
}

export interface PresignResult {
  url:        string;
  method:     "PUT";
  key:        string;
  expiresAt:  number;  // Unix seconds
}

/**
 * Generate a SigV4 presigned PUT URL for an R2 object.
 * The client must issue a PUT with the exact Content-Type used here.
 */
export async function presignPut(
  cfg: PresignConfig,
  key: string,
  contentType: string,
): Promise<PresignResult> {
  const endpoint = `https://${cfg.accountId}.r2.cloudflarestorage.com`;
  const url = new URL(`/${cfg.bucket}/${key}`, endpoint);

  const client = new AwsClient({
    accessKeyId:     cfg.accessKeyId,
    secretAccessKey: cfg.secretAccessKey,
    region:          "auto",
    service:         "s3",
  });

  // aws4fetch presigns by creating a signed URL with X-Amz-Expires
  const signedReq = await client.sign(
    new Request(url.toString(), {
      method:  "PUT",
      headers: { "Content-Type": contentType },
    }),
    {
      aws:  { signQuery: true },
      // @ts-ignore — aws4fetch extended option
      expiresIn: cfg.expiresIn,
    },
  );

  return {
    url:       signedReq.url,
    method:    "PUT",
    key,
    expiresAt: Math.floor(Date.now() / 1000) + cfg.expiresIn,
  };
}
```

## Worker API Endpoint: Issue Upload URL

```typescript
// src/handlers/upload.ts
import { presignPut }  from "../lib/r2-presign";
import { verifyAccessJWT } from "../lib/access-jwt";

export interface Env {
  R2_ACCOUNT_ID:        string;
  R2_ACCESS_KEY_ID:     string;
  R2_SECRET_ACCESS_KEY: string;
  R2_BUCKET:            string;
  CLOUDFLARE_TEAM_DOMAIN: string;
  ACCESS_AUD_TAG:       string;
  DB:                   D1Database;
}

const ALLOWED_TYPES: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png":  "png",
  "image/webp": "webp",
  "application/pdf": "pdf",
};

export async function handleUploadRequest(req: Request, env: Env): Promise<Response> {
  // 1. Verify Cloudflare Access JWT
  const token = req.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) return new Response("unauthorized", { status: 401 });

  let identity;
  try {
    identity = await verifyAccessJWT(token, {
      teamDomain:  env.CLOUDFLARE_TEAM_DOMAIN,
      audienceTag: env.ACCESS_AUD_TAG,
    });
  } catch {
    return new Response("forbidden", { status: 403 });
  }

  // 2. Parse and validate request body
  let body: { contentType: string; filename: string; orgId: string };
  try {
    body = await req.json();
  } catch {
    return new Response("invalid JSON", { status: 400 });
  }

  const ext = ALLOWED_TYPES[body.contentType];
  if (!ext) {
    return new Response(`unsupported content type: ${body.contentType}`, { status: 415 });
  }

  // 3. Build a scoped, collision-resistant key
  const objectId = crypto.randomUUID();
  const key = `uploads/${body.orgId}/${identity.sub}/${objectId}.${ext}`;

  // 4. Record pending upload in D1 (confirmed via post-upload flow)
  await env.DB.prepare(
    `INSERT INTO pending_uploads (id, org_id, user_id, r2_key, content_type, created_at)
     VALUES (?, ?, ?, ?, ?, unixepoch())`,
  )
    .bind(objectId, body.orgId, identity.sub, key, body.contentType)
    .run();

  // 5. Issue presigned URL (60 second expiry — tight window)
  const result = await presignPut(
    {
      accountId:       env.R2_ACCOUNT_ID,
      accessKeyId:     env.R2_ACCESS_KEY_ID,
      secretAccessKey: env.R2_SECRET_ACCESS_KEY,
      bucket:          env.R2_BUCKET,
      expiresIn:       60,
    },
    key,
    body.contentType,
  );

  return new Response(
    JSON.stringify({ uploadId: objectId, presignedUrl: result.url, key, expiresAt: result.expiresAt }),
    { headers: { "Content-Type": "application/json" } },
  );
}
```

## Post-Upload Confirmation Worker

```typescript
// src/handlers/confirm-upload.ts
export async function handleConfirmUpload(req: Request, env: Env): Promise<Response> {
  const { uploadId } = (await req.json()) as { uploadId: string };

  // Verify the object actually landed in R2
  const obj = await env.R2_BUCKET_BINDING.head(`uploads/${uploadId}`).catch(() => null);
  if (!obj) {
    return new Response("object not found in R2", { status: 404 });
  }

  // Move from pending_uploads to assets
  const { results } = await env.DB
    .prepare("SELECT * FROM pending_uploads WHERE id = ?")
    .bind(uploadId)
    .all();

  if (results.length === 0) {
    return new Response("upload record not found", { status: 404 });
  }

  const pending = results[0] as { r2_key: string; org_id: string; user_id: string; content_type: string };

  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO assets (id, org_id, user_id, r2_key, content_type, created_at)
       VALUES (?, ?, ?, ?, ?, unixepoch())`,
    ).bind(uploadId, pending.org_id, pending.user_id, pending.r2_key, pending.content_type),
    env.DB.prepare("DELETE FROM pending_uploads WHERE id = ?").bind(uploadId),
  ]);

  return new Response(JSON.stringify({ assetId: uploadId, key: pending.r2_key }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

## Terraform: R2 Bucket and API Token

```hcl
# terraform/cloudflare-r2-upload.tf
resource "cloudflare_r2_bucket" "uploads" {
  account_id = var.cloudflare_account_id
  name       = "orchords-uploads-${var.environment}"
  location   = "WEUR"
}

# Scoped API token: R2 write on this bucket only
resource "cloudflare_api_token" "r2_upload" {
  name = "orchords-r2-upload-${var.environment}"

  policy {
    effect = "allow"
    resources = {
      "com.cloudflare.edge.r2.bucket.${var.cloudflare_account_id}_default_orchords-uploads-${var.environment}" = "*"
    }
    permission_groups = [
      { id = data.cloudflare_api_token_permission_groups.all.r2["Workers R2 Storage Bucket Item Write"] },
    ]
  }
}

# Inject credentials as Worker secrets
resource "cloudflare_workers_secret" "r2_key_id" {
  account_id  = var.cloudflare_account_id
  script_name = var.worker_script_name
  name        = "R2_ACCESS_KEY_ID"
  text        = cloudflare_api_token.r2_upload.id
}

resource "cloudflare_workers_secret" "r2_secret" {
  account_id  = var.cloudflare_account_id
  script_name = var.worker_script_name
  name        = "R2_SECRET_ACCESS_KEY"
  text        = sha256(cloudflare_api_token.r2_upload.value)  # derived per S3 compat docs
}
```

## Client-Side Upload (TypeScript Browser)

```typescript
// frontend/upload.ts
async function uploadFile(file: File, orgId: string): Promise<string> {
  // 1. Request presigned URL from your Worker
  const resp = await fetch("/api/upload", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ contentType: file.type, filename: file.name, orgId }),
  });
  if (!resp.ok) throw new Error(`presign failed: ${resp.status}`);

  const { uploadId, presignedUrl } = (await resp.json()) as {
    uploadId: string;
    presignedUrl: string;
    key: string;
    expiresAt: number;
  };

  // 2. PUT directly to R2 — Worker is not in the upload path
  const put = await fetch(presignedUrl, {
    method:  "PUT",
    body:    file,
    headers: { "Content-Type": file.type },
  });
  if (!put.ok) throw new Error(`R2 PUT failed: ${put.status}`);

  // 3. Confirm the upload with your Worker
  const confirm = await fetch("/api/upload/confirm", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ uploadId }),
  });
  if (!confirm.ok) throw new Error(`confirm failed: ${confirm.status}`);

  const { assetId } = (await confirm.json()) as { assetId: string; key: string };
  return assetId;
}
```

## Anti-patterns

- **Issuing presigned URLs with long expiry (> 15 min)**: a leaked URL allows unauthorized uploads
  during the entire expiry window; keep expiry to 60–300 seconds.
- **No post-upload verification step**: without confirming the object landed in R2, `pending_uploads`
  rows accumulate forever, and you may reference non-existent objects in `assets`.
- **Routing the binary through the Worker**: defeats the purpose; the Worker should only sign the
  URL, not proxy the bytes.
- **Using the account-level R2 API token**: scope tokens to the specific bucket and Write-only
  permissions; a leaked token should not expose all R2 data.

## Gotchas

- R2's S3-compatible endpoint requires `region = "auto"` in SigV4 signing; using `us-east-1` or
  other AWS regions will produce signature mismatches.
- The `Content-Type` header must match between the signature and the actual PUT request; a mismatch
  yields a 403. Enforce this by including `Content-Type` in the presigned headers.
- R2 presigned URL expiry is based on the signing timestamp, not the server's clock; ensure the
  Worker's `Date` is accurate (it is — Workers use the Cloudflare global time).
- `aws4fetch` must be bundled; it is not available as a global in the Workers runtime.
- CORS: if the browser PUT comes from a different origin than R2, configure the R2 bucket CORS
  policy via `cloudflare_r2_bucket_cors_configuration` in Terraform.

## Verification

```bash
# Request a presigned URL from your Worker
PRESIGN=$(curl -s -X POST https://api.example.com/upload \
  -H "Content-Type: application/json" \
  -d '{"contentType":"image/png","filename":"test.png","orgId":"org1"}')

URL=$(echo "$PRESIGN" | jq -r '.presignedUrl')
UPLOAD_ID=$(echo "$PRESIGN" | jq -r '.uploadId')

# Upload a test file directly to R2
curl -v -X PUT "$URL" \
  -H "Content-Type: image/png" \
  --data-binary @test.png

# Confirm
curl -s -X POST https://api.example.com/upload/confirm \
  -H "Content-Type: application/json" \
  -d "{\"uploadId\":\"$UPLOAD_ID\"}" | jq .

# Verify object exists in R2 via wrangler
npx wrangler r2 object head "orchords-uploads-production/uploads/org1/..." \
  --bucket orchords-uploads-production
```

## Related

- `cloudflare-r2-backup-restore-strategy.md` — R2 backup and lifecycle
- `terraform-cloudflare-r2-cors-lifecycle.md` — CORS and lifecycle via Terraform
- `r2-cross-account-replication-workers.md` — cross-account R2 replication
- `cloudflare-access-jwt-workers-validation.md` — JWT identity validation
- `cloudflare-workers-api-token-scoping.md` — API token scoping best practices

## Sources

- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/r2/api/s3/api/
- https://github.com/mhart/aws4fetch
- https://developers.cloudflare.com/r2/buckets/cors/
- https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-query-string-auth.html
