# R2 Presigned URL Upload Flow with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Users need to upload large files (images, videos, documents) directly to Cloudflare R2 without routing megabytes through your Worker. You want the Worker to issue a short-lived presigned URL, the client to PUT directly to R2, and the metadata (R2 key, size, MIME type) to be recorded in D1 after the upload completes.

## Context

Cloudflare R2 supports S3-compatible presigned URLs via the `aws4fetch` library and the S3-compat API, but the **Workers binding API** (`env.BUCKET`) also exposes `createMultipartUpload()` and `createPresignedUrl()` (available via the `R2Bucket` binding). Presigned uploads let clients bypass the Worker for data transfer — critical when files exceed the 100 MB Worker request body limit or when you want to avoid CPU time costs on raw byte streaming.

The flow:
1. Client requests a presigned URL from your Worker (authenticated).
2. Worker generates the URL, stores a pending upload record in D1, and returns the URL + key.
3. Client PUTs the file directly to R2 using the presigned URL.
4. Client notifies the Worker of completion.
5. Worker verifies the object exists in R2, updates the D1 record to `confirmed`.

---

## Full Implementation

```typescript
// src/worker.ts

import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export interface Env {
  // R2 bucket binding (used for existence check and metadata)
  BUCKET: R2Bucket;
  // D1 database binding
  DB: D1Database;
  // R2 S3-compat credentials (for presigning; R2 binding cannot presign directly)
  R2_ACCOUNT_ID: string;
  R2_ACCESS_KEY_ID: string;
  R2_SECRET_ACCESS_KEY: string;
  R2_BUCKET_NAME: string;
  // Auth
  API_SECRET: string;
}

function getS3Client(env: Env): S3Client {
  return new S3Client({
    region: "auto",
    endpoint: `https://${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: env.R2_ACCESS_KEY_ID,
      secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    },
  });
}

interface PresignRequest {
  filename: string;
  contentType: string;
  sizeBytes: number;
  userId: string;
}

async function handlePresign(request: Request, env: Env): Promise<Response> {
  const body = await request.json<PresignRequest>();

  // Validate MIME type allowlist
  const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp", "video/mp4", "application/pdf"];
  if (!ALLOWED_TYPES.includes(body.contentType)) {
    return Response.json({ error: "Unsupported content type" }, { status: 400 });
  }

  // Max 500 MB
  if (body.sizeBytes > 500 * 1024 * 1024) {
    return Response.json({ error: "File too large" }, { status: 400 });
  }

  // Generate a unique R2 key
  const key = `uploads/${body.userId}/${crypto.randomUUID()}-${body.filename}`;

  // Create presigned PUT URL (valid for 15 minutes)
  const s3 = getS3Client(env);
  const command = new PutObjectCommand({
    Bucket: env.R2_BUCKET_NAME,
    Key: key,
    ContentType: body.contentType,
    ContentLength: body.sizeBytes,
  });
  const presignedUrl = await getSignedUrl(s3, command, { expiresIn: 900 });

  // Store pending upload record in D1
  await env.DB.prepare(
    `INSERT INTO uploads (id, user_id, r2_key, content_type, size_bytes, status, created_at)
     VALUES (?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)`
  )
    .bind(crypto.randomUUID(), body.userId, key, body.contentType, body.sizeBytes)
    .run();

  return Response.json({ presignedUrl, key });
}

async function handleConfirm(request: Request, env: Env): Promise<Response> {
  const { key, userId } = await request.json<{ key: string; userId: string }>();

  // Verify the object actually landed in R2
  const object = await env.BUCKET.head(key);
  if (!object) {
    return Response.json({ error: "Object not found in R2" }, { status: 404 });
  }

  // Update D1 record — also capture the final size and ETag from R2
  const result = await env.DB.prepare(
    `UPDATE uploads
     SET status = 'confirmed', etag = ?, confirmed_at = CURRENT_TIMESTAMP
     WHERE r2_key = ? AND user_id = ? AND status = 'pending'`
  )
    .bind(object.httpEtag, key, userId)
    .run();

  if (result.meta.changes === 0) {
    return Response.json({ error: "Upload record not found or already confirmed" }, { status: 404 });
  }

  return Response.json({ confirmed: true, size: object.size, etag: object.httpEtag });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Simple API key auth
    if (request.headers.get("x-api-key") !== env.API_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    if (request.method === "POST" && url.pathname === "/upload/presign") {
      return handlePresign(request, env);
    }
    if (request.method === "POST" && url.pathname === "/upload/confirm") {
      return handleConfirm(request, env);
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Client-Side Upload Flow

```typescript
// client/upload.ts  — runs in the browser

async function uploadFile(file: File, userId: string, apiKey: string): Promise<string> {
  // Step 1: Get presigned URL
  const presignRes = await fetch("/upload/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-api-key": apiKey },
    body: JSON.stringify({
      filename: file.name,
      contentType: file.type,
      sizeBytes: file.size,
      userId,
    }),
  });
  const { presignedUrl, key } = await presignRes.json<{ presignedUrl: string; key: string }>();

  // Step 2: PUT directly to R2 — no size limit from the Worker's perspective
  const uploadRes = await fetch(presignedUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
    // Note: do NOT send x-api-key here; it goes directly to R2
  });
  if (!uploadRes.ok) throw new Error(`R2 upload failed: ${uploadRes.status}`);

  // Step 3: Notify Worker to confirm and persist metadata
  const confirmRes = await fetch("/upload/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-api-key": apiKey },
    body: JSON.stringify({ key, userId }),
  });
  if (!confirmRes.ok) throw new Error("Upload confirmation failed");

  return key; // The R2 key is now safe to store as a reference
}
```

---

## D1 Schema

```sql
CREATE TABLE uploads (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL,
  r2_key       TEXT NOT NULL UNIQUE,
  content_type TEXT NOT NULL,
  size_bytes   INTEGER NOT NULL,
  etag         TEXT,
  status       TEXT NOT NULL DEFAULT 'pending', -- pending | confirmed | deleted
  created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  confirmed_at TEXT
);
CREATE INDEX idx_uploads_user ON uploads(user_id, status);
```

---

## Anti-patterns

- **Streaming the file body through the Worker** — defeats the purpose of presigned URLs and hits the 100 MB Worker body limit.
- **Skipping the confirmation step** — a presigned URL can be generated but never used; without confirmation, `uploads` fills with ghost `pending` rows. Add a cleanup Cron to delete `pending` records older than 1 hour.
- **Setting `contentType` from the server without trusting the client-declared MIME** — validate and allowlist on the server, then set `httpMetadata.contentType` to the validated value. Do not infer from the filename alone.
- **Using the R2 binding to presign** — the Workers binding `R2Bucket` does not expose presigned URL generation as of 2026-08; use the S3-compatible API via `@aws-sdk/s3-request-presigner`.

## Gotchas

- The presigned URL contains your R2 credentials embedded in the query string. Treat it as a secret; do not log it.
- R2 presigned PUTs require the `Content-Length` header from the client. Browsers set this automatically for `fetch` with a `File` body, but some HTTP clients omit it.
- `env.BUCKET.head(key)` returns `null` if the object does not exist — always null-check before accessing properties.
- Presigned URL expiry (`expiresIn`) is wall-clock seconds. If the client's clock is skewed, the URL may appear expired before the real TTL elapses.

## Verification

```bash
# 1. Get a presigned URL
PRESIGN=$(curl -s -X POST https://api.example.com/upload/presign \
  -H 'x-api-key: secret' \
  -H 'Content-Type: application/json' \
  -d '{"filename":"test.jpg","contentType":"image/jpeg","sizeBytes":1234,"userId":"u1"}' \
  | jq -r '.presignedUrl')

# 2. PUT a small test file directly to R2
curl -X PUT "$PRESIGN" \
  -H 'Content-Type: image/jpeg' \
  --data-binary @test.jpg

# 3. Confirm
curl -s -X POST https://api.example.com/upload/confirm \
  -H 'x-api-key: secret' \
  -H 'Content-Type: application/json' \
  -d '{"key":"uploads/u1/...","userId":"u1"}'
# Expected: {"confirmed":true,"size":1234,...}
```

## Related

- `workers-analytics-engine-custom-dashboard.md`
- `workers-d1-sqlite-edge-queries.md`
- `cloudflare-images-transform-workers.md`

## Sources

- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://docs.aws.amazon.com/AWSJavaScriptSDK/v3/latest/modules/_aws_sdk_s3_request_presigner.html
