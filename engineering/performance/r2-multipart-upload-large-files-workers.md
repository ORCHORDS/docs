# R2 Multipart Upload for Large Files in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Uploading files larger than 100 MB to Cloudflare R2 through a Worker fails with a request-size limit error or times out because Workers have a maximum request body size limit and a CPU time limit per request. Multipart upload splits the file into 10 MB chunks, uploads parts in parallel, and completes the upload in a final API call — enabling reliable transfers of files up to 5 TB. Resumable upload state stored in KV lets clients retry interrupted uploads without restarting from the beginning.

---

## Context
R2's multipart upload API mirrors the S3 Multipart Upload specification. A client initiates an upload and receives an `uploadId`. It then uploads numbered parts (each at least 5 MB, except the last), receiving an `ETag` per part. Finally it calls `completeMultipartUpload` with the ordered list of `{ partNumber, etag }` pairs. Workers stream the client's request body through `ReadableStream` so the Worker itself never holds the entire file in memory. Abandoned multipart uploads (where the client dropped the connection) must be cleaned up with a `listMultipartUploads` + `abortMultipartUpload` cycle; a Cron Trigger handles this automatically. KV stores the in-progress upload state (uploadId, completed parts) keyed by a client-supplied upload token so clients can resume after a network interruption.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "r2-multipart"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "uploads"

[[kv_namespaces]]
binding = "UPLOAD_STATE"
id = "<your-kv-namespace-id>"

[triggers]
crons = ["0 3 * * *"]  # cleanup abandoned uploads daily at 03:00 UTC
```

## Section 2 — Implementation

```typescript
// src/index.ts
import type { R2Bucket, KVNamespace } from '@cloudflare/workers-types';

export interface Env {
  BUCKET: R2Bucket;
  UPLOAD_STATE: KVNamespace;
}

/** Minimum part size enforced by R2 (except the last part). */
const MIN_PART_SIZE = 5 * 1024 * 1024;   // 5 MB
/** Target part size for parallel uploads. */
const PART_SIZE     = 10 * 1024 * 1024;  // 10 MB
/** Abandon uploads older than this many seconds. */
const ABANDON_TTL   = 24 * 60 * 60;      // 24 h

interface UploadState {
  uploadId: string;
  key: string;
  parts: Array<{ partNumber: number; etag: string }>;
  createdAt: number;
}

export default {
  // ── scheduled handler — runs daily to clean up abandoned uploads ───────
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    console.log('[cleanup] scanning for abandoned multipart uploads');
    const listed = await env.BUCKET.listMultipartUploads?.();
    if (!listed) return;
    const cutoff = Date.now() - ABANDON_TTL * 1000;
    for (const upload of listed.objects) {
      // @ts-expect-error listMultipartUploads is a non-standard R2 extension
      const initiated: number = upload.initiated?.getTime() ?? 0;
      if (initiated < cutoff) {
        // @ts-expect-error
        await env.BUCKET.abortMultipartUpload(upload.key, upload.uploadId);
        await env.UPLOAD_STATE.delete(`mpu:${upload.uploadId}`);
        console.log(`[cleanup] aborted ${upload.key} / ${upload.uploadId}`);
      }
    }
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // ── POST /upload/initiate — start a new multipart upload ────────────
    if (request.method === 'POST' && url.pathname === '/upload/initiate') {
      const { key } = await request.json<{ key: string }>();
      if (!key) return new Response('Missing key', { status: 400 });

      const mpu = await env.BUCKET.createMultipartUpload(key, {
        httpMetadata: { contentType: 'application/octet-stream' },
      });

      const state: UploadState = {
        uploadId: mpu.uploadId,
        key,
        parts: [],
        createdAt: Date.now(),
      };
      await env.UPLOAD_STATE.put(
        `mpu:${mpu.uploadId}`,
        JSON.stringify(state),
        { expirationTtl: ABANDON_TTL }
      );

      return Response.json({ uploadId: mpu.uploadId, key });
    }

    // ── PUT /upload/part — upload a single part ──────────────────────────
    if (request.method === 'PUT' && url.pathname === '/upload/part') {
      const uploadId  = url.searchParams.get('uploadId');
      const partNumber = Number(url.searchParams.get('partNumber'));
      const key        = url.searchParams.get('key');

      if (!uploadId || !partNumber || !key || !request.body) {
        return new Response('Missing params or body', { status: 400 });
      }

      const stateJson = await env.UPLOAD_STATE.get(`mpu:${uploadId}`, 'json') as UploadState | null;
      if (!stateJson) return new Response('Upload not found', { status: 404 });

      // R2 resumable handle
      const mpu = env.BUCKET.resumeMultipartUpload(key, uploadId);

      const t0 = performance.now();
      const part = await mpu.uploadPart(partNumber, request.body);
      const elapsed = performance.now() - t0;
      console.log(`[mpu] part ${partNumber} uploaded in ${elapsed.toFixed(0)} ms, etag=${part.etag}`);

      // Persist part metadata for the final complete call
      stateJson.parts.push({ partNumber, etag: part.etag });
      stateJson.parts.sort((a, b) => a.partNumber - b.partNumber);
      await env.UPLOAD_STATE.put(
        `mpu:${uploadId}`,
        JSON.stringify(stateJson),
        { expirationTtl: ABANDON_TTL }
      );

      return Response.json({ partNumber, etag: part.etag });
    }

    // ── POST /upload/complete — finalise the multipart upload ───────────
    if (request.method === 'POST' && url.pathname === '/upload/complete') {
      const { uploadId, key } = await request.json<{ uploadId: string; key: string }>();

      const stateJson = await env.UPLOAD_STATE.get(`mpu:${uploadId}`, 'json') as UploadState | null;
      if (!stateJson) return new Response('Upload not found', { status: 404 });

      const mpu = env.BUCKET.resumeMultipartUpload(key, uploadId);

      const t0 = performance.now();
      const obj = await mpu.complete(stateJson.parts);
      const elapsed = performance.now() - t0;
      console.log(`[mpu] completed key=${key} in ${elapsed.toFixed(0)} ms, etag=${obj.etag}`);

      // Clean up state
      await env.UPLOAD_STATE.delete(`mpu:${uploadId}`);

      return Response.json({ key: obj.key, etag: obj.etag, size: obj.size });
    }

    // ── DELETE /upload/abort — cancel and clean up ───────────────────────
    if (request.method === 'DELETE' && url.pathname === '/upload/abort') {
      const { uploadId, key } = await request.json<{ uploadId: string; key: string }>();
      const mpu = env.BUCKET.resumeMultipartUpload(key, uploadId);
      await mpu.abort();
      await env.UPLOAD_STATE.delete(`mpu:${uploadId}`);
      return new Response(null, { status: 204 });
    }

    return new Response('Not Found', { status: 404 });
  },
};

// ── Client-side helper (browser / Node.js) ───────────────────────────────
// Place in src/client.ts or call from your front-end build.
export async function uploadLargeFile(
  file: File | Blob,
  key: string,
  workerBase: string
): Promise<{ key: string; etag: string; size: number }> {
  // 1. Initiate
  const { uploadId } = await fetch(`${workerBase}/upload/initiate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key }),
  }).then((r) => r.json<{ uploadId: string }>());

  // 2. Slice into 10 MB parts and upload in parallel batches of 4
  const totalParts = Math.ceil(file.size / PART_SIZE);
  const BATCH = 4;

  for (let batch = 0; batch < totalParts; batch += BATCH) {
    const batchParts = Array.from({ length: Math.min(BATCH, totalParts - batch) }, (_, i) => {
      const partNumber = batch + i + 1;
      const start = (partNumber - 1) * PART_SIZE;
      const end = Math.min(start + PART_SIZE, file.size);
      return { partNumber, slice: file.slice(start, end) };
    });

    await Promise.all(
      batchParts.map(({ partNumber, slice }) =>
        fetch(`${workerBase}/upload/part?uploadId=${uploadId}&partNumber=${partNumber}&key=<redacted-secret> {
          method: 'PUT',
          body: slice,
        })
      )
    );
  }

  // 3. Complete
  return fetch(`${workerBase}/upload/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uploadId, key }),
  }).then((r) => r.json<{ key: string; etag: string; size: number }>());
}
```

## Section 3 — Benchmark / Verification

```bash
# Generate a 150 MB test file
dd if=/dev/urandom of=/tmp/test-150mb.bin bs=1M count=150

# Initiate
UPLOAD_ID=$(curl -s -X POST https://r2-multipart.<account>.workers.dev/upload/initiate \
  -H 'Content-Type: application/json' \
  -d '{"key":"test/150mb.bin"}' | jq -r .uploadId)
echo "uploadId: $UPLOAD_ID"

# Upload parts (3 × 50 MB split into 10 MB chunks = 15 parts)
for i in $(seq 1 15); do
  START=$(( (i-1) * 10 * 1024 * 1024 ))
  dd if=/tmp/test-150mb.bin bs=1 skip=$START count=$((10*1024*1024)) 2>/dev/null | \
  curl -s -X PUT \
    "https://r2-multipart.<account>.workers.dev/upload/part?uploadId=$UPLOAD_ID&partNumber=$i&key=<redacted-secret> \
    --data-binary @- &
done
wait

# Complete
curl -s -X POST https://r2-multipart.<account>.workers.dev/upload/complete \
  -H 'Content-Type: application/json' \
  -d "{\"uploadId\":\"$UPLOAD_ID\",\"key\":\"test/150mb.bin\"}" | jq .
```

---

## Anti-patterns
- **Uploading the entire file as a single Workers request** — The Workers request body limit (100 MB by default, 500 MB for Unbound) causes failures for large files; always use multipart for files > 50 MB.
- **Skipping KV state persistence** — Without persisted part ETags, a network interruption requires restarting the upload from part 1; always store and update the state after each part.
- **Not aborting abandoned uploads** — Incomplete multipart uploads accrue R2 storage costs; always run a cleanup Cron and provide a client-side `abort` path.
- **Setting part sizes below 5 MB** — R2 rejects parts smaller than 5 MB (except the final part); using 10 MB parts is safer and reduces per-request overhead.

---

## Gotchas
- `resumeMultipartUpload` does not make a network call — it returns a lightweight handle; only `uploadPart` and `complete` make requests.
- Part numbers must be between 1 and 10,000 and must be passed in ascending order to `complete`; the array is sorted in the state-persistence step to guarantee this.
- KV `expirationTtl` is set on the state entry so it automatically expires if the upload is never completed or aborted — this prevents orphaned KV entries from accumulating.
- The Cron cleanup handler uses a non-standard `listMultipartUploads` API; confirm availability in your `compatibility_date` release notes before relying on it.

---

## Verification

```bash
# List in-progress multipart uploads via wrangler
npx wrangler r2 object list uploads --prefix test/

# Tail Worker logs during upload
npx wrangler tail --format pretty

# Confirm the object exists after completion
npx wrangler r2 object get uploads/test/150mb.bin --file /tmp/downloaded.bin
ls -lh /tmp/downloaded.bin
```

---

## Related
- `workers-request-coalescing-durable-objects.md`
- `workers-prefetch-speculation-rules-pages.md`

---

## Sources
- Cloudflare R2 Multipart Upload — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#r2multipartupload
- S3 Multipart Upload Guide — https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html
- Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
