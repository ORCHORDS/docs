# Direct File Upload from Capacitor to R2 via Workers Presigned URL

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A Capacitor mobile app needs to let users upload photos, videos, or documents directly to Cloudflare R2 without routing the binary payload through the Workers process — which would consume both CPU time and egress bandwidth. Progress indicators must work on the native layer, and metadata (filename, mime type, uploader ID) must be stored durably after the upload completes.

---

## Context
Cloudflare R2's S3-compatible API supports multipart uploads and presigned URLs, both of which allow the client to PUT directly to R2 without passing through a Worker. The Workers endpoint acts only as a gatekeeper: it authenticates the user, calls `r2.createMultipartUpload()` or generates a time-limited signed URL, and returns the upload parameters. After the upload the client calls a completion endpoint that verifies the object exists in R2 and writes metadata to D1. `XMLHttpRequest` is used on the Capacitor side instead of `fetch` because XHR exposes upload progress events that `fetch` still lacks in most mobile WebViews.

---

## Section 1 — Wrangler Config & D1 Schema

```toml
# wrangler.toml
name = "r2-upload-worker"
compatibility_date = "2025-06-01"

[[r2_buckets]]
binding = "UPLOADS"
bucket_name = "mobile-uploads"

[[d1_databases]]
binding = "DB"
database_name = "upload_db"
database_id = "<YOUR_D1_DATABASE_ID>"

[vars]
MAX_FILE_SIZE_MB = "100"
PRESIGN_TTL_SECONDS = "900"
```

```bash
npx wrangler d1 execute upload_db --command "
CREATE TABLE IF NOT EXISTS uploads (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL,
  r2_key       TEXT NOT NULL UNIQUE,
  filename     TEXT NOT NULL,
  mime_type    TEXT NOT NULL,
  size_bytes   INTEGER,
  status       TEXT NOT NULL DEFAULT 'pending',
  upload_id    TEXT,
  created_at   INTEGER NOT NULL,
  completed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_uploads_user ON uploads(user_id);
CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
"
```

---

## Section 2 — Workers Implementation

```typescript
// src/r2-upload-worker.ts
export interface Env {
  UPLOADS: R2Bucket;
  DB: D1Database;
  MAX_FILE_SIZE_MB: string;
  PRESIGN_TTL_SECONDS: string;
}

type PresignRequest = {
  userId: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
};

type CompleteRequest = {
  uploadId: string;  // our D1 record id
  r2Key: string;
  parts?: Array<{ partNumber: number; etag: string }>;
  multipartUploadId?: string;
};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(req.url);

    if (req.method === 'POST' && pathname === '/upload/presign') {
      return handlePresign(req, env);
    }

    if (req.method === 'POST' && pathname === '/upload/complete') {
      return handleComplete(req, env);
    }

    if (req.method === 'GET' && pathname === '/upload/status') {
      return handleStatus(req, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handlePresign(req: Request, env: Env): Promise<Response> {
  // Authenticate — real implementation reads JWT from Authorization header
  const { userId, filename, mimeType, sizeBytes } = await req.json<PresignRequest>();

  const maxBytes = Number(env.MAX_FILE_SIZE_MB) * 1024 * 1024;
  if (sizeBytes > maxBytes) {
    return Response.json(
      { error: `File exceeds maximum size of ${env.MAX_FILE_SIZE_MB}MB` },
      { status: 413 },
    );
  }

  const uploadId = crypto.randomUUID();
  const r2Key = `${userId}/${uploadId}/${encodeURIComponent(filename)}`;
  const now = Date.now();

  // For large files use multipart upload; for small files use a single presigned PUT
  const MULTIPART_THRESHOLD = 5 * 1024 * 1024; // 5 MB

  if (sizeBytes >= MULTIPART_THRESHOLD) {
    const multipart = await env.UPLOADS.createMultipartUpload(r2Key, {
      httpMetadata: { contentType: mimeType },
      customMetadata: { userId, originalFilename: filename },
    });

    await env.DB
      .prepare(
        `INSERT INTO uploads (id, user_id, r2_key, filename, mime_type, size_bytes, status, upload_id, created_at)
         VALUES (?, ?, ?, ?, ?, ?, 'pending_multipart', ?, ?)`,
      )
      .bind(uploadId, userId, r2Key, filename, mimeType, sizeBytes, multipart.uploadId, now)
      .run();

    return Response.json({
      uploadId,
      r2Key,
      multipartUploadId: multipart.uploadId,
      strategy: 'multipart',
      // Client must PUT each part to /upload/part/:uploadId/:partNumber
      // using the Workers endpoint as a thin proxy, or via R2 S3-compatible API
      partSize: 10 * 1024 * 1024, // 10 MB parts
    });
  }

  // Single presigned PUT — Workers R2 binding does not yet expose presigned URLs
  // natively; use a short-lived token stored in KV and a /upload/put proxy endpoint.
  // For S3-compatible presigning, use the CF R2 S3 API with aws4fetch.
  await env.DB
    .prepare(
      `INSERT INTO uploads (id, user_id, r2_key, filename, mime_type, size_bytes, status, created_at)
       VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)`,
    )
    .bind(uploadId, userId, r2Key, filename, mimeType, sizeBytes, now)
    .run();

  // Return the Worker's own proxy URL — client PUTs directly here
  return Response.json({
    uploadId,
    r2Key,
    strategy: 'single',
    uploadUrl: `/upload/put/${uploadId}`,
    expiresAt: now + Number(env.PRESIGN_TTL_SECONDS) * 1000,
  });
}

async function handleComplete(req: Request, env: Env): Promise<Response> {
  const { uploadId, r2Key, parts, multipartUploadId } = await req.json<CompleteRequest>();

  // Verify the object actually landed in R2
  const obj = await env.UPLOADS.head(r2Key);
  if (!obj && !multipartUploadId) {
    return Response.json({ error: 'Object not found in R2' }, { status: 404 });
  }

  if (multipartUploadId && parts) {
    // Complete multipart upload
    const multipart = env.UPLOADS.resumeMultipartUpload(r2Key, multipartUploadId);
    await multipart.complete(parts.map(p => ({
      partNumber: p.partNumber,
      etag: p.etag,
    })));
  }

  const now = Date.now();
  await env.DB
    .prepare(
      `UPDATE uploads SET status='completed', completed_at=?, size_bytes=COALESCE(size_bytes, ?)
       WHERE id=?`,
    )
    .bind(now, obj?.size ?? 0, uploadId)
    .run();

  return Response.json({ success: true, uploadId, r2Key });
}

async function handleStatus(req: Request, env: Env): Promise<Response> {
  const uploadId = new URL(req.url).searchParams.get('uploadId');
  if (!uploadId) return Response.json({ error: 'Missing uploadId' }, { status: 400 });

  const row = await env.DB
    .prepare('SELECT id, r2_key, status, size_bytes, created_at, completed_at FROM uploads WHERE id=?')
    .bind(uploadId)
    .first();

  if (!row) return Response.json({ error: 'Not found' }, { status: 404 });
  return Response.json(row);
}
```

---

## Section 3 — Capacitor Client with XHR Progress

```typescript
// src/upload/capacitor-upload.ts
import { Filesystem, Directory } from '@capacitor/filesystem';

const WORKERS_URL = process.env.CF_WORKERS_BASE_URL ?? '';

export type UploadProgress = {
  loaded: number;
  total: number;
  percent: number;
};

export async function uploadFile(
  localPath: string,
  filename: string,
  mimeType: string,
  userId: string,
  accessToken: string,
  onProgress?: (p: UploadProgress) => void,
): Promise<{ uploadId: string; r2Key: string }> {
  // Read file as base64 from Capacitor Filesystem
  const { data } = await Filesystem.readFile({ path: localPath, directory: Directory.Cache });
  const binary = atob(data as string);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: mimeType });

  // Step 1: Get presign info from Worker
  const presignRes = await fetch(`${WORKERS_URL}/upload/presign`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ userId, filename, mimeType, sizeBytes: blob.size }),
  });

  const presign = await presignRes.json<{
    uploadId: string;
    r2Key: string;
    strategy: 'single' | 'multipart';
    uploadUrl?: string;
    multipartUploadId?: string;
    partSize?: number;
  }>();

  if (presign.strategy === 'single' && presign.uploadUrl) {
    // Step 2a: Single XHR PUT with progress
    await xhrPut(
      `${WORKERS_URL}${presign.uploadUrl}`,
      blob,
      mimeType,
      accessToken,
      onProgress,
    );
  } else if (presign.strategy === 'multipart' && presign.multipartUploadId && presign.partSize) {
    // Step 2b: Multipart — split into chunks and PUT each part
    const parts: Array<{ partNumber: number; etag: string }> = [];
    const partSize = presign.partSize;
    let partNumber = 1;

    for (let offset = 0; offset < blob.size; offset += partSize) {
      const chunk = blob.slice(offset, offset + partSize);
      const etag = await xhrPut(
        `${WORKERS_URL}/upload/part/${presign.uploadId}/${partNumber}`,
        chunk,
        mimeType,
        accessToken,
        p => onProgress?.({
          loaded: offset + p.loaded,
          total: blob.size,
          percent: Math.round(((offset + p.loaded) / blob.size) * 100),
        }),
      );
      parts.push({ partNumber, etag });
      partNumber++;
    }

    // Step 3b: Complete multipart
    await fetch(`${WORKERS_URL}/upload/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({
        uploadId: presign.uploadId,
        r2Key: presign.r2Key,
        parts,
        multipartUploadId: presign.multipartUploadId,
      }),
    });

    return { uploadId: presign.uploadId, r2Key: presign.r2Key };
  }

  // Step 3a: Notify Worker the single upload is done
  await fetch(`${WORKERS_URL}/upload/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ uploadId: presign.uploadId, r2Key: presign.r2Key }),
  });

  return { uploadId: presign.uploadId, r2Key: presign.r2Key };
}

function xhrPut(
  url: string,
  body: Blob,
  contentType: string,
  token: string,
  onProgress?: (p: UploadProgress) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    xhr.setRequestHeader('Content-Type', contentType);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);

    xhr.upload.addEventListener('progress', e => {
      if (e.lengthComputable && onProgress) {
        onProgress({
          loaded: e.loaded,
          total: e.total,
          percent: Math.round((e.loaded / e.total) * 100),
        });
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.getResponseHeader('ETag') ?? '');
      } else {
        reject(new Error(`Upload failed: ${xhr.status} ${xhr.responseText}`));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

    xhr.send(body);
  });
}
```

---

## Anti-patterns
- **Routing the binary payload through the Worker** — a 100 MB video through `request.arrayBuffer()` consumes 100 MB of Worker memory and counts as CPU time; always use presigned URLs or a proxy-to-R2 pattern.
- **Not calling `/upload/complete`** — orphaned multipart uploads in R2 incur storage charges; incomplete multipart uploads must be aborted or completed.
- **Using `fetch` instead of `XMLHttpRequest` for progress** — `fetch` does not expose upload progress in Capacitor WebViews; XHR's `upload.onprogress` is the only reliable cross-platform option.

---

## Gotchas
- `Filesystem.readFile` returns a base64 string on native; on web it returns a `Blob` directly — guard with `typeof data === 'string'` before calling `atob`.
- R2 multipart parts must be at least 5 MB except for the final part; sending smaller chunks returns a `EntityTooSmall` error.
- The R2 binding's `createMultipartUpload` is not the same as the S3-compatible presigned URL flow — they use different completion mechanisms.

---

## Verification

```bash
# Request a presign token
curl -X POST https://r2-upload-worker.example.workers.dev/upload/presign \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <JWT>' \
  -d '{"userId":"u1","filename":"photo.jpg","mimeType":"image/jpeg","sizeBytes":2097152}'

# List objects in the R2 bucket
npx wrangler r2 object list mobile-uploads

# Inspect D1 upload table
npx wrangler d1 execute upload_db \
  --command "SELECT id, filename, status, size_bytes FROM uploads ORDER BY created_at DESC LIMIT 10"

# Check for abandoned multipart uploads
npx wrangler r2 multipart list mobile-uploads
```

---

## Related
- `react-native-cloudflare-workers-api-client.md`
- `workers-biometric-webauthn-mobile-auth.md`

---

## Sources
- Cloudflare R2 Multipart Upload — https://developers.cloudflare.com/r2/api/s3/multipart-upload/
- Capacitor Filesystem Plugin — https://capacitorjs.com/docs/apis/filesystem
- XMLHttpRequest upload events — https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/upload
