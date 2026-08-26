# R2 Multipart Upload Failures: Lessons from Production

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Our media pipeline allows users to upload video files up to 10 GB directly to R2 via a presigned multipart flow coordinated by a Cloudflare Worker. After launch we saw:

- Upload sessions accumulating as "incomplete" uploads — never cleaned up, accruing storage cost
- ETags collected from part uploads occasionally mismatched what R2 expected at `completeMultipartUpload` time
- Large concurrent uploads from the same user sometimes completing with corrupt part ordering
- Client retries after a network blip creating duplicate parts and confusing our part manifest
- Abort calls silently failing, leaving zombie upload sessions for weeks

---

## Context

R2 multipart upload follows the S3-compatible API:

1. `createMultipartUpload` → returns `uploadId`
2. `uploadPart` (one per chunk) → returns an `ETag` per part
3. `completeMultipartUpload` (with ordered ETag list) → object materialised
4. `abortMultipartUpload` on any failure to reclaim storage

The minimum part size is **5 MB** (except the last part). The maximum part count is **10 000**. Each part's ETag is an opaque string — it must be stored exactly as returned, including any surrounding quotes.

We initially treated the ETag as just an identifier for logging; we trimmed whitespace, lowercased it, and stripped surrounding double-quotes from the raw response header. All three of those transformations caused `completeMultipartUpload` to fail with `InvalidPart`.

---

## Solution

### 1. Coordinator Worker — create and track upload sessions

```typescript
// workers/src/upload-coordinator.ts

import type { R2MultipartUpload, R2UploadedPart } from '@cloudflare/workers-types';

interface Env {
  MEDIA_BUCKET: R2Bucket;
  UPLOAD_SESSIONS: KVNamespace; // stores uploadId → metadata
}

interface UploadSession {
  uploadId: string;
  key: string;
  parts: R2UploadedPart[];
  createdAt: number;
  totalParts: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    switch (url.pathname) {
      case '/upload/create': return handleCreate(request, env);
      case '/upload/part-url': return handlePartUrl(request, env);
      case '/upload/complete': return handleComplete(request, env);
      case '/upload/abort': return handleAbort(request, env);
      default: return new Response('Not Found', { status: 404 });
    }
  },
} satisfies ExportedHandler<Env>;

async function handleCreate(request: Request, env: Env): Promise<Response> {
  const { key, totalParts } = await request.json<{ key: string; totalParts: number }>();

  if (!key || totalParts < 1 || totalParts > 10_000) {
    return Response.json({ error: 'invalid parameters' }, { status: 400 });
  }

  const mpu: R2MultipartUpload = await env.MEDIA_BUCKET.createMultipartUpload(key, {
    httpMetadata: { contentType: 'application/octet-stream' },
    customMetadata: { initiatedBy: request.headers.get('x-user-id') ?? 'unknown' },
  });

  const session: UploadSession = {
    uploadId: mpu.uploadId,
    key,
    parts: [],
    createdAt: Date.now(),
    totalParts,
  };

  // Store session with 48-hour TTL as a safety net
  await env.UPLOAD_SESSIONS.put(
    `session:${mpu.uploadId}`,
    JSON.stringify(session),
    { expirationTtl: 48 * 60 * 60 },
  );

  return Response.json({ uploadId: mpu.uploadId });
}

async function handleComplete(request: Request, env: Env): Promise<Response> {
  const { uploadId, parts } = await request.json<{
    uploadId: string;
    parts: Array<{ partNumber: number; etag: string }>;
  }>();

  const raw = await env.UPLOAD_SESSIONS.get(`session:${uploadId}`);
  if (!raw) return Response.json({ error: 'session not found' }, { status: 404 });

  const session: UploadSession = JSON.parse(raw);

  // Sort by partNumber — critical: out-of-order parts produce corrupt objects
  const ordered = [...parts].sort((a, b) => a.partNumber - b.partNumber);

  const mpu = env.MEDIA_BUCKET.resumeMultipartUpload(session.key, uploadId);

  const obj = await mpu.complete(ordered);

  // Clean up session record on success
  await env.UPLOAD_SESSIONS.delete(`session:${uploadId}`);

  return Response.json({ key: obj.key, etag: obj.httpEtag });
}

async function handleAbort(request: Request, env: Env): Promise<Response> {
  const { uploadId } = await request.json<{ uploadId: string }>();

  const raw = await env.UPLOAD_SESSIONS.get(`session:${uploadId}`);
  if (!raw) return Response.json({ error: 'session not found' }, { status: 404 });

  const session: UploadSession = JSON.parse(raw);
  const mpu = env.MEDIA_BUCKET.resumeMultipartUpload(session.key, uploadId);

  // abort() throws if the uploadId is already complete or already aborted
  try {
    await mpu.abort();
  } catch (err) {
    // Log but do not fail the request — object may already be gone
    console.warn('abort failed (may already be complete/aborted):', err);
  }

  await env.UPLOAD_SESSIONS.delete(`session:${uploadId}`);
  return Response.json({ aborted: true });
}

async function handlePartUrl(_request: Request, _env: Env): Promise<Response> {
  // In our architecture the client uploads parts directly via presigned URLs
  // generated here; actual upload goes client → R2, not through the Worker.
  // Part URL generation logic omitted for brevity.
  return Response.json({ url: 'presigned-url-here' });
}
```

### 2. Client-side part upload with correct ETag capture

```typescript
// client/src/upload.ts

const MIN_PART_SIZE = 5 * 1024 * 1024; // 5 MB

interface UploadedPart {
  partNumber: number;
  etag: string; // raw ETag from response header — do NOT transform
}

export async function uploadFileMultipart(
  file: File,
  coordinatorBase: string,
): Promise<string> {
  const key = `uploads/${Date.now()}-${file.name}`;

  // Calculate part count (enforce minimum part size)
  const partSize = Math.max(MIN_PART_SIZE, Math.ceil(file.size / 10_000));
  const totalParts = Math.ceil(file.size / partSize);

  const { uploadId } = await fetch(`${coordinatorBase}/upload/create`, {
    method: 'POST',
    body: JSON.stringify({ key, totalParts }),
  }).then(r => r.json<{ uploadId: string }>());

  const uploadedParts: UploadedPart[] = [];

  for (let partNumber = 1; partNumber <= totalParts; partNumber++) {
    const start = (partNumber - 1) * partSize;
    const end = Math.min(start + partSize, file.size);
    const chunk = file.slice(start, end);

    const etag = await uploadPartWithRetry(uploadId, partNumber, chunk);
    uploadedParts.push({ partNumber, etag });
  }

  const { key: finalKey } = await fetch(`${coordinatorBase}/upload/complete`, {
    method: 'POST',
    body: JSON.stringify({ uploadId, parts: uploadedParts }),
  }).then(r => r.json<{ key: string }>());

  return finalKey;
}

async function uploadPartWithRetry(
  uploadId: string,
  partNumber: number,
  chunk: Blob,
  maxRetries = 3,
): Promise<string> {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      // In a real implementation, fetch a presigned URL from the coordinator.
      // Here we demonstrate the critical ETag capture pattern.
      const response = await fetch(`/r2-presigned-part?uploadId=${uploadId}&partNumber=${partNumber}`, {
        method: 'PUT',
        body: chunk,
      });

      if (!response.ok) throw new Error(`Part upload failed: ${response.status}`);

      // CRITICAL: capture ETag exactly as returned — quotes and all
      const etag = response.headers.get('ETag');
      if (!etag) throw new Error('No ETag in response');

      // Do NOT trim, lowercase, or strip quotes — return verbatim
      return etag;
    } catch (err) {
      if (attempt === maxRetries) throw err;
      // Exponential backoff: 1s, 2s, 4s
      await new Promise(resolve => setTimeout(resolve, 1000 * 2 ** (attempt - 1)));
    }
  }
  throw new Error('unreachable');
}
```

### 3. Stale upload cleanup Cron Worker

```typescript
// workers/src/upload-cleanup.ts

interface Env {
  MEDIA_BUCKET: R2Bucket;
  UPLOAD_SESSIONS: KVNamespace;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = Date.now() - 24 * 60 * 60 * 1000; // 24 hours ago

    let cursor: string | undefined;
    let cleaned = 0;

    do {
      const list = await env.UPLOAD_SESSIONS.list({
        prefix: 'session:',
        cursor,
        limit: 100,
      });

      for (const key of list.keys) {
        const raw = await env.UPLOAD_SESSIONS.get(key.name);
        if (!raw) continue;

        const session: { uploadId: string; key: string; createdAt: number } = JSON.parse(raw);

        if (session.createdAt < cutoff) {
          const mpu = env.MEDIA_BUCKET.resumeMultipartUpload(session.key, session.uploadId);
          try {
            await mpu.abort();
          } catch {
            // already completed or aborted
          }
          await env.UPLOAD_SESSIONS.delete(key.name);
          cleaned++;
        }
      }

      cursor = list.list_complete ? undefined : list.cursor;
    } while (cursor);

    console.log(`Cleanup complete. Aborted ${cleaned} stale multipart uploads.`);
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

### Part size math

| File size | Recommended part size | Parts |
|-----------|----------------------|-------|
| < 50 MB | 5 MB (minimum) | 1–10 |
| 50 MB – 1 GB | 10 MB | 5–100 |
| 1 GB – 10 GB | 50–100 MB | 10–200 |

Using the minimum 5 MB everywhere works but wastes retry bandwidth. We settled on `Math.max(5MB, Math.ceil(fileSize / 100))` as a sensible default that keeps parts ≤ 100 regardless of file size.

### Concurrent uploads

Uploading all parts in parallel is tempting. In practice, saturating the user's connection caused browser-side timeouts. We use a concurrency pool of 4:

```typescript
async function uploadPartsWithPool(
  parts: Array<{ partNumber: number; chunk: Blob }>,
  uploadId: string,
  concurrency = 4,
): Promise<UploadedPart[]> {
  const results: UploadedPart[] = [];
  const queue = [...parts];

  async function worker(): Promise<void> {
    while (queue.length) {
      const item = queue.shift();
      if (!item) break;
      const etag = await uploadPartWithRetry(uploadId, item.partNumber, item.chunk);
      results.push({ partNumber: item.partNumber, etag });
    }
  }

  await Promise.all(Array.from({ length: concurrency }, worker));
  return results.sort((a, b) => a.partNumber - b.partNumber);
}
```

---

## Anti-patterns

- **Transforming ETags**: stripping quotes, lowercasing, or trimming whitespace from ETags breaks `completeMultipartUpload` with `InvalidPart`.
- **Not calling abort on failure**: incomplete uploads are billed as storage. Always abort on error, even network errors mid-part.
- **Assuming part order from upload order**: parallel uploads finish out of order. Always sort by `partNumber` before calling `complete`.
- **Using the Worker as a proxy for part data**: routing gigabytes through a Worker hits the 128 MB request body limit and burns CPU time. Use presigned URLs so clients upload directly to R2.
- **No cleanup Cron**: zombie upload sessions accumulate. A daily cleanup Cron is not optional.

---

## Gotchas

- `resumeMultipartUpload` does **not** validate that the `uploadId` exists at construction time — it only fails when you call a method. Don't assume a successful constructor means a valid session.
- The R2 API returns ETags with surrounding double-quotes in the HTTP response header (e.g., `"abc123"`). The S3-compatible ETag format requires these quotes to be preserved when building the complete request.
- If a client retries a part upload after a timeout, two parts with the same `partNumber` may exist. R2 accepts the last successfully uploaded part for each number — but your session manifest must reflect the latest ETag, not the first.
- R2 multipart uploads are not visible via `list()` until `completeMultipartUpload` is called. You cannot use `MEDIA_BUCKET.list()` to discover orphaned uploads — you must track them in KV.

---

## Verification

```typescript
// tests/multipart.test.ts
import { describe, it, expect } from 'vitest';
import { env } from 'cloudflare:test';

describe('R2 multipart upload', () => {
  it('completes a 3-part upload in correct order', async () => {
    const key = 'test/multipart-order';
    const mpu = await env.MEDIA_BUCKET.createMultipartUpload(key);

    const part1 = await env.MEDIA_BUCKET.uploadPart(key, mpu.uploadId, 1, new Uint8Array(5 * 1024 * 1024).fill(1));
    const part2 = await env.MEDIA_BUCKET.uploadPart(key, mpu.uploadId, 2, new Uint8Array(5 * 1024 * 1024).fill(2));
    const part3 = await env.MEDIA_BUCKET.uploadPart(key, mpu.uploadId, 3, new Uint8Array(1024).fill(3));

    // Intentionally pass in reverse order to test our sort logic
    const obj = await mpu.complete([part3, part1, part2].sort((a, b) => a.partNumber - b.partNumber));

    expect(obj.key).toBe(key);
    const head = await env.MEDIA_BUCKET.head(key);
    expect(head?.size).toBe(5 * 1024 * 1024 * 2 + 1024);
  });

  it('abort cleans up the session', async () => {
    const key = 'test/multipart-abort';
    const mpu = await env.MEDIA_BUCKET.createMultipartUpload(key);
    await mpu.abort();
    // After abort, completing should throw
    await expect(mpu.complete([])).rejects.toThrow();
  });
});
```

---

## Related

- `documentation/docs/policies/lessons/workers-secret-rotation-zero-downtime-lessons.md`
- `documentation/docs/policies/lessons/kv-cache-stampede-lessons.md`
- `documentation/docs/policies/lessons/workers-durable-objects-storage-lessons.md`

---

## Sources

- Cloudflare R2 multipart upload: https://developers.cloudflare.com/r2/api/workers/workers-api-usage/#multipart-upload
- R2 limits: https://developers.cloudflare.com/r2/platform/limits/
- S3 multipart upload: https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html
