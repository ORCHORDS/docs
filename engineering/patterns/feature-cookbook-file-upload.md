# feature-cookbook-file-upload

**Issue:** File upload — R2, presigned URLs, multipart
**Date:** 2026-08-09
**Status:** documented

## Symptom
Users upload 100MB videos. They send the file to your
Worker. The Worker times out at 30s. The upload fails.
The user retries. The upload fails again.

## Root cause
**Large uploads through a Worker don't work.** Use
presigned URLs.

**Source:** R2 docs.

## The "presigned URL" pattern

For large uploads, R2 presigned URLs:
```ts
// 1. Generate a presigned URL
const url = await env.R2!.createPresignedUrl({
  key: `uploads/${userId}/${fileName}`,
  expiration: 3600,  // 1 hour
  method: 'PUT',
  httpMetadata: {
    contentType: 'video/mp4',
  },
});

// 2. Send the URL to the client
return Response.json({ uploadUrl: url, key });

// 3. Client uploads directly to R2
await fetch(url, { method: 'PUT', body: file });
```

The upload bypasses the Worker.

## The "multipart upload" pattern

For very large files (> 1GB):
```ts
// 1. Create a multipart upload
const multipart = await env.R2!.createMultipartUpload({
  key: `uploads/${userId}/${fileName}`,
});

// 2. Get URLs for each part
const partCount = Math.ceil(file.size / (5 * 1024 * 1024));  // 5MB parts
const urls = [];
for (let i = 0; i < partCount; i++) {
  const url = await env.R2!.createPresignedUrl({
    key: multipart.key,
    expiration: 3600,
    method: 'PUT',
    partNumber: i + 1,
    uploadId: multipart.uploadId,
  });
  urls.push(url);
}

// 3. Client uploads each part
// 4. Client calls completeMultipartUpload with the parts
```

The upload is in parts.

## The "file validation" pattern

For validation, check the file:
```ts
async function validateFile(file: File): Promise<{ valid: boolean; error?: string }> {
  // 1. Check the size
  const MAX_SIZE = 100 * 1024 * 1024;  // 100MB
  if (file.size > MAX_SIZE) {
    return { valid: false, error: 'File too large' };
  }

  // 2. Check the type
  const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'video/mp4'];
  if (!ALLOWED_TYPES.includes(file.type)) {
    return { valid: false, error: 'Invalid file type' };
  }

  // 3. Check the name
  if (file.name.length > 255) {
    return { valid: false, error: 'File name too long' };
  }

  return { valid: true };
}
```

The validation is server-side.

## The "virus scan" pattern

For a virus scan, use a service:
```ts
async function scanFile(key: string, env: Env): Promise<{ clean: boolean }> {
  const obj = await env.R2!.get(key);
  const buffer = await obj!.arrayBuffer();

  // Send to virus scan service (e.g. ClamAV)
  const response = await fetch('https://scan.example.com/scan', {
    method: 'POST',
    body: buffer,
  });

  const result = await response.json();
  return { clean: result.clean };
}
```

The file is scanned.

## The "image processing" pattern

For image processing, use CF Image Resizing:
```ts
const imageUrl = `https://example.com/cdn-cgi/image/width=200,quality=80,format=auto/${key}`;
```

CF resizes the image.

## The "thumbnail" pattern

For thumbnails, generate on upload:
```ts
async function generateThumbnail(key: string, env: Env): Promise<void> {
  const obj = await env.R2!.get(key);
  if (!obj) return;

  // Use a Worker to resize
  const image = await fetch(`https://example.com/cdn-cgi/image/width=200/${key}`);
  const buffer = await image.arrayBuffer();

  await env.R2!.put(key.replace(/\.[^.]+$/, '_thumb.webp'), buffer, {
    httpMetadata: { contentType: 'image/webp' },
  });
}
```

The thumbnail is generated.

## The "upload progress" pattern

For progress, use a callback:
```ts
async function uploadWithProgress(file: File, url: string, onProgress: (percent: number) => void): Promise<void> {
  const xhr = new XMLHttpRequest();

  xhr.upload.addEventListener('progress', (e) => {
    if (e.lengthComputable) {
      onProgress((e.loaded / e.total) * 100);
    }
  });

  xhr.open('PUT', url);
  xhr.send(file);
}
```

The progress is shown.

## The "upload" metadata

For metadata, store in D1:
```sql
CREATE TABLE uploads (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  key TEXT NOT NULL,
  filename TEXT NOT NULL,
  size INTEGER NOT NULL,
  content_type TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The metadata is in the DB.

## The "upload security" pattern

For security, scan + restrict:
- **Auth:** User must be authenticated
- **Type:** Whitelist content types
- **Size:** Cap the size
- **Name:** Sanitize the name
- **Scan:** Virus scan

```ts
// Sanitize the name
function sanitizeName(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 255);
}
```

The upload is secure.

## The "upload anti-pattern" anti-patterns

### 1. Upload through Worker
- **Issue:** Worker times out for large files
- **Fix:** Use presigned URL

### 2. No validation
- **Issue:** Malicious files uploaded
- **Fix:** Validate + scan

### 3. No metadata
- **Issue:** Files are unsearchable
- **Fix:** Store metadata in DB

### 4. No progress
- **Issue:** User doesn't know status
- **Fix:** Progress callback

### 5. No multipart
- **Issue:** Large files fail
- **Fix:** Multipart upload

## Verification
- **Test:** Upload works
- **Test:** Validation works
- **Test:** Progress is accurate
- **Live:** Upload is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "upload through Worker" anti-pattern.** Use
  presigned URL.
- **The "no validation" anti-pattern.** Validate.
- **The "no metadata" anti-pattern.** Store metadata.

## Related
- `cloudflare/r2-large-file-patterns.md`
- `feature-cookbook-data-import.md`
- `feature-cookbook-data-warehouse.md`
- `feature-cookbook-comms-channels.md`
- R2: https://developers.cloudflare.com/r2/
- CF Image Resizing: https://developers.cloudflare.com/images/
