# r2-large-file-patterns

**Issue:** Use R2 for large files — multipart, presigned URLs
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want users to upload 100MB videos. You accept the file
in the Worker. The Worker reads 100MB into memory. The
Worker hits the 128MB memory limit. The upload fails.

## Root cause
**Workers have a memory limit.** For large files, use
multipart upload or direct-to-R2 presigned URLs.

**Source:** CF R2:
https://developers.cloudflare.com/r2/

> "R2 is S3-compatible object storage with no egress
> fees."

## The "presigned URL" pattern

The client uploads directly to R2; the Worker is not in
the path:
```ts
// Server: generate a presigned URL
async function getUploadUrl(filename: string, env: Env): Promise<{ url: string; key: string }> {
  const key = `uploads/${crypto.randomUUID()}/${filename}`;
  const url = await env.R2!.createPresignedUrl({
    method: 'PUT',
    key,
    expiration: 600,  // 10 min
  });
  return { url, key };
}

// Client: upload directly to R2
const { url, key } = await fetch('/api/uploads/presign', {
  method: 'POST',
  body: JSON.stringify({ filename: 'video.mp4' }),
}).then(r => r.json());

await fetch(url, { method: 'PUT', body: file });

// Client: notify the server
await fetch('/api/uploads', {
  method: 'POST',
  body: JSON.stringify({ key, size: file.size, contentType: file.type }),
});
```

The Worker is not in the data path; the upload goes
directly to R2.

## The "multipart upload" pattern

For very large files (> 100 MB), use multipart:
```ts
// Server: create a multipart upload
const multipart = await env.R2!.createMultipartUpload(key, {
  httpMetadata: { contentType: 'video/mp4' },
});

// Client: upload parts
const partSize = 10 * 1024 * 1024;  // 10 MB
for (let i = 0; i < file.size; i += partSize) {
  const part = file.slice(i, i + partSize);
  const uploadResult = await multipart.uploadPart(i / partSize + 1, part);
  // ... save uploadResult
}

// Server: complete the multipart upload
await multipart.complete([...]);
```

Multipart is parallelizable (multiple parts at once) and
resumable (re-upload only failed parts).

## The "download presigned URL" pattern

For private files, generate a presigned URL:
```ts
async function getDownloadUrl(key: string, env: Env): Promise<string> {
  return env.R2!.createPresignedUrl({
    method: 'GET',
    key,
    expiration: 3600,  // 1 hour
  });
}
```

The user can download with the URL; the URL expires.

## The "R2 vs Workers binding" pattern

There are two ways to use R2 from a Worker:
1. **R2 binding** (built-in, no HTTP)
2. **S3 API** (HTTP, works with any S3-compatible tool)

For most Workers, the R2 binding is simpler:
```ts
// Upload
await env.R2!.put(key, value);

// Download
const value = await env.R2!.get(key);

// List
const list = await env.R2!.list({ prefix: 'uploads/' });

// Delete
await env.R2!.delete(key);
```

For external tools, use the S3 API.

## The "R2 + CDN" pattern

For public files, R2 + CF's CDN is free + fast:
```ts
const object = await env.R2!.get(key);
if (!object) return new Response('Not found', { status: 404 });

const headers = new Headers();
object.writeHttpMetadata(headers);
headers.set('etag', object.httpEtag);
headers.set('cache-control', 'public, max-age=31536000, immutable');

return new Response(object.body, { headers });
```

CF caches the file at the edge. Free egress; fast delivery.

## The "R2 lifecycle" pattern

For automatic cleanup of old files:
```bash
# CF dashboard: R2 → bucket → Settings → Lifecycle rules
# Or via API
```

Common rules:
- Delete objects > 90 days old
- Move to Infrequent Access after 30 days
- Delete incomplete multipart uploads after 7 days

## The "R2 event notifications" pattern

For "trigger a Worker on file upload":
1. Set up an event notification (in CF dashboard or API)
2. The notification triggers a queue
3. The queue worker processes the event

```ts
// The queue worker
export default {
  async queue(batch: MessageBatch<R2Event>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      if (message.body.action === 'PutObject') {
        // Process the upload
        await processUpload(message.body.object.key, env);
      }
      message.ack();
    }
  },
};
```

## The "R2 + DO" pattern

For per-user storage, use a DO as the index:
```ts
// In the DO
async storeFile(filename: string, content: ArrayBuffer, env: Env): Promise<string> {
  const key = `users/${this.userId}/${crypto.randomUUID()}/${filename}`;
  await env.R2!.put(key, content);

  await this.storage.put(`file:${key}`, {
    filename,
    size: content.byteLength,
    uploadedAt: new Date().toISOString()
  });
  return key;
}

async listFiles(): Promise<FileMetadata[]> {
  const list = await this.storage.list({ prefix: 'file:' });
  return Array.from(list.values());
}
```

The DO holds the metadata; R2 holds the bytes.

## The "R2 cost" pattern

R2 costs:
- **Storage:** $0.015 per GB-month
- **Class A operations (PUT, POST, LIST):** $4.50 per million
- **Class B operations (GET, HEAD):** $0.36 per million
- **Egress:** FREE (CF's killer feature)

For 10 TB of storage, 10M reads, 1M writes per month:
- Storage: $150
- Reads: $3.60
- Writes: $4.50
- Egress: $0
- Total: ~$158/month

S3 would be $1000+/month with the same traffic.

## The "R2 + presigned URL security" pattern

Presigned URLs are signed; only the holder can upload/
download. The URL expires. The user can:
- Upload to a specific key only
- Upload within the expiration time
- Upload with a specific content type (if signed)

For sensitive files, add a content-type restriction:
```ts
const url = await env.R2!.createPresignedUrl({
  method: 'PUT',
  key,
  expiration: 600,
  httpMetadata: { contentType: 'image/jpeg' },  // Limit content type
});
```

## Verification
- **Test:** `test/upload.test.ts > presigned URL works for
  upload + download` — passes
- **Live:** R2 usage + costs are monitored
- **Audit:** Quarterly review of storage patterns

## Gotchas
- **The "Worker has 128MB memory" gotcha.** A 100MB file in
  the Worker exceeds the limit. Use presigned URLs.
- **The "R2 is eventually consistent" gotcha.** A write may
  not be visible for up to 60s globally. Don't rely on
  read-after-write.
- **The "R2 has no folders" gotcha.** R2 has flat
  namespaces; "folders" are just key prefixes.
- **The "R2 is not a database" gotcha.** Don't query R2
  (no indexes, no JOINs). Use D1 for queries; R2 for blobs.
- **The "presigned URLs can leak" gotcha.** A presigned URL
  is a bearer token. Don't log it; don't put it in a
  public place.

## Related
- `cloudflare/r2-signed-urls.md`
- `patterns/feature-cookbook.md` (upload + download)
- `cloudflare/durable-objects-patterns.md` (DO + R2)
- `cloudflare/cost-optimization-cloudflare.md`
- CF R2: https://developers.cloudflare.com/r2/
- R2 S3 API: https://developers.cloudflare.com/r2/api/s3/api/
