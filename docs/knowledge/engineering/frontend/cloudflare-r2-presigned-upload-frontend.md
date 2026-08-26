# Cloudflare R2 Presigned Uploads from the Browser

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Users need to upload large files (images, videos, documents) from your frontend app to cloud storage without routing the binary payload through your Worker, which would consume CPU time and risk hitting the 100 MB request body limit.

## Context
Cloudflare R2 supports S3-compatible presigned URLs, allowing a Worker to generate a time-limited `PUT` URL that the browser uses to upload directly to R2 over HTTPS. The Worker authenticates the user, enforces size and MIME type policies, and creates the presigned URL using the AWS Signature V4 algorithm via `aws4fetch`. The binary never passes through the Worker itself. Multipart upload (for files > 5 GB or resumable uploads) uses a separate presigned flow.

## Worker: Generate Presigned PUT URL

```typescript
// src/routes/upload-url.ts
import { Hono } from 'hono';
import { AwsClient } from 'aws4fetch';
import { z } from 'zod';
import { zValidator } from '@hono/zod-validator';

export type Env = {
  R2_ACCOUNT_ID: string;
  R2_ACCESS_KEY_ID: string;
  R2_SECRET_ACCESS_KEY: string;
  R2_BUCKET_NAME: string;
  USER_UPLOADS: R2Bucket; // for post-upload validation via binding
};

const uploadSchema = z.object({
  filename: z.string().min(1).max(255),
  contentType: z.enum(['image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'application/pdf']),
  sizeBytes: z.number().int().positive().max(500 * 1024 * 1024), // 500 MB max
});

const uploadApp = new Hono<{ Bindings: Env }>();

uploadApp.post(
  '/upload-url',
  zValidator('json', uploadSchema),
  async (c) => {
    const { filename, contentType, sizeBytes } = c.req.valid('json');

    // Scope upload keys by user ID (set by auth middleware upstream)
    const userId = c.get('userId' as never) as string ?? 'anonymous';
    const key = `uploads/${userId}/${Date.now()}-${crypto.randomUUID()}-${filename}`;

    const r2Endpoint = `https://${c.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`;
    const aws = new AwsClient({
      accessKeyId: c.env.R2_ACCESS_KEY_ID,
      secretAccessKey: c.env.R2_SECRET_ACCESS_KEY,
      service: 's3',
      region: 'auto',
    });

    // Presign a PUT request — expires in 15 minutes
    const url = new URL(`${r2Endpoint}/${c.env.R2_BUCKET_NAME}/${key}`);
    url.searchParams.set('X-Amz-Expires', '900');

    const signed = await aws.sign(
      new Request(url.toString(), {
        method: 'PUT',
        headers: {
          'Content-Type': contentType,
          'Content-Length': sizeBytes.toString(),
        },
      }),
      { aws: { signQuery: true } }
    );

    return c.json({
      uploadUrl: signed.url,
      key,
      expiresAt: new Date(Date.now() + 900_000).toISOString(),
    });
  }
);

export default uploadApp;
```

## Browser: Upload with Progress Tracking

```typescript
// src/lib/uploadToR2.ts

export interface UploadResult {
  key: string;
  etag: string | null;
}

export async function uploadToR2(
  file: File,
  onProgress?: (percent: number) => void
): Promise<UploadResult> {
  // 1. Request a presigned URL from your Worker
  const meta = await fetch('/api/upload-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filename: file.name,
      contentType: file.type,
      sizeBytes: file.size,
    }),
  });
  if (!meta.ok) throw new Error(`Failed to get upload URL: ${meta.status}`);
  const { uploadUrl, key } = await meta.json() as { uploadUrl: string; key: string };

  // 2. Upload directly to R2 — use XMLHttpRequest for progress events
  const etag = await new Promise<string | null>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', uploadUrl);
    xhr.setRequestHeader('Content-Type', file.type);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.getResponseHeader('ETag'));
      } else {
        reject(new Error(`R2 upload failed: ${xhr.status} ${xhr.statusText}`));
      }
    });
    xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

    xhr.send(file);
  });

  return { key, etag };
}
```

## React Upload Component

```tsx
// src/components/FileUpload.tsx
import { useState, useCallback } from 'react';
import { uploadToR2 } from '../lib/uploadToR2';

export function FileUpload({ onComplete }: { onComplete: (key: string) => void }) {
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setProgress(0);

    try {
      const { key } = await uploadToR2(file, setProgress);
      setProgress(100);
      onComplete(key);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setProgress(null);
    }
  }, [onComplete]);

  return (
    <div>
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf"
        onChange={handleChange}
        disabled={progress !== null && progress < 100}
        aria-label="Upload file"
      />
      {progress !== null && (
        <progress value={progress} max={100} aria-label="Upload progress">
          {progress}%
        </progress>
      )}
      {error && <p role="alert" style={{ color: 'red' }}>{error}</p>}
    </div>
  );
}
```

## Worker: Post-Upload Webhook Validation

```typescript
// src/routes/upload-complete.ts — called by the frontend after the PUT succeeds
// to verify the file actually landed in R2 and trigger downstream processing

import { Hono } from 'hono';
import type { Env } from './upload-url';

const completeApp = new Hono<{ Bindings: Env }>();

completeApp.post('/upload-complete', async (c) => {
  const { key, etag } = await c.req.json<{ key: string; etag: string }>();

  // Verify the object exists in R2 (prevents spoofed completion calls)
  const obj = await c.env.USER_UPLOADS.head(key);
  if (!obj) return c.json({ error: 'Object not found in R2' }, 404);

  // Validate ETag matches (ETags are MD5 hashes for single-part uploads)
  const normalizedEtag = etag.replace(/"/g, '');
  if (obj.etag !== normalizedEtag) {
    return c.json({ error: 'ETag mismatch — upload may be corrupt' }, 409);
  }

  // Queue downstream processing (resize, virus scan, etc.)
  // await c.env.QUEUE.send({ type: 'process-upload', key, contentType: obj.httpMetadata?.contentType });

  return c.json({ status: 'accepted', key, size: obj.size });
});

export default completeApp;
```

## R2 CORS Configuration

```json
// Apply via: wrangler r2 bucket cors put my-bucket --rules cors-rules.json
[
  {
    "AllowedOrigins": ["https://app.example.com"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["Content-Type", "Content-Length"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

## Anti-patterns
- Setting `AllowedOrigins: ["*"]` on the R2 CORS rule — any site can then upload to your bucket using a stolen presigned URL
- Not validating `sizeBytes` on the Worker before generating the presigned URL — a client can send a large `Content-Length` and the presigned URL will accept it up to R2's limit
- Storing the raw presigned URL in `localStorage` — it expires but leaks the signed credentials; generate URLs on demand
- Using `fetch()` for large uploads instead of `XMLHttpRequest` — `fetch` does not expose upload progress events natively (Streams API `ReadableStream.tee` can work but adds complexity)
- Skipping the post-upload verification step — without it, you cannot detect failed uploads or clients that claim completion without uploading

## Gotchas
- R2 presigned URLs use `X-Amz-*` query parameters (AWS Signature V4); the `Content-Type` in the presigned request must exactly match the `Content-Type` header sent by the browser PUT — a mismatch returns `403 SignatureDoesNotMatch`
- `aws4fetch` signs the request including the `Content-Length` header — if the browser sends a different size (e.g., after compression), the signature is invalid
- R2 ETags are MD5 of the raw object bytes for single-part uploads, but are opaque identifiers for multipart uploads — do not rely on ETags for integrity checking in the multipart case
- Presigned URLs bypass R2 bucket public access settings — a signed URL for a private-bucket object is accessible to anyone with the URL until it expires
- The `User-Uploads` R2 binding and the S3-compatible endpoint point to the same bucket — use the binding (`.head()`, `.get()`) for server-side verification and the S3 endpoint for presigned client-side operations

## Verification
```bash
# Generate a presigned URL and test the PUT
URL=$(curl -s -X POST https://my-worker.workers.dev/api/upload-url \
  -H 'Content-Type: application/json' \
  -d '{"filename":"test.jpg","contentType":"image/jpeg","sizeBytes":12345}' \
  | jq -r '.uploadUrl')

curl -X PUT "$URL" -H 'Content-Type: image/jpeg' --data-binary @test.jpg -v

# Verify the object landed in R2
wrangler r2 object get my-bucket uploads/anonymous/... --file /tmp/downloaded.jpg
```

## Related
- [Browser File System Access](browser-file-system-access.md)
- [File Upload UX Chunked Resumable](file-upload-ux-chunked-resumable.md)
- [Hono Cloudflare Workers Frontend API](hono-cloudflare-workers-frontend-api.md)
- [Form Validation Zod Workers Endpoint](form-validation-zod-workers-endpoint.md)

## Sources
- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/r2/buckets/cors/
- https://github.com/mhart/aws4fetch
- https://developers.cloudflare.com/r2/runtime-apis/
