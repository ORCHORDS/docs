# Capacitor File Picker → Workers Presigned URL → R2 Direct Upload

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Users need to select arbitrary files (PDFs, ZIPs, Office documents, audio) from their device
storage and upload them directly to Cloudflare R2 without routing the binary payload through
your Workers function. The camera-upload pattern (`@capacitor/camera` + presigned PUT) does not
apply here because the file picker returns a URI or base64 blob, not a camera frame, and files
can be hundreds of megabytes.

---

## Context

Capacitor's official `@capacitor/filesystem` gives you file read access but no picker UI.
The community plugin `@capawesome-team/capacitor-file-picker` provides a native file-picker
sheet on iOS (UIDocumentPickerViewController) and Android (Intent.ACTION_OPEN_DOCUMENT) and
returns either a base64 string or a file URI. The upload path that avoids memory pressure is:

1. Native picker returns a local `file://` URI.
2. App calls a Workers endpoint to obtain an R2 presigned upload URL.
3. App streams the file directly to R2 using `fetch` with the presigned URL.
4. Workers confirms the upload via an R2 metadata call and records the result in D1.

This keeps the Workers function lightweight — it only issues credentials and records metadata —
while R2 handles the actual binary transfer from the edge closest to the device.

---

## Plugin Installation

```bash
npm install @capawesome-team/capacitor-file-picker
npx cap sync
```

iOS — add to `Info.plist` if you need iCloud Drive access:
```xml
<key>UISupportsDocumentBrowser</key>
<true/>
<key>LSSupportsOpeningDocumentsInPlace</key>
<false/>
```

Android — no extra manifest entries required for `ACTION_OPEN_DOCUMENT`.

---

## Workers: Presigned URL Endpoint

```typescript
// workers/src/upload-presign.ts
import { R2Bucket, D1Database } from "@cloudflare/workers-types";

interface Env {
  UPLOADS: R2Bucket;
  DB: D1Database;
  UPLOAD_SECRET: string;
}

interface PresignRequest {
  filename: string;
  contentType: string;
  sizeBytes: number;
  userId: string;
}

const MAX_UPLOAD_BYTES = 500 * 1024 * 1024; // 500 MB
const PRESIGN_TTL_SECONDS = 300; // 5 minutes

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = (await request.json()) as PresignRequest;

    if (!body.filename || !body.contentType || !body.sizeBytes || !body.userId) {
      return new Response("Missing required fields", { status: 400 });
    }

    if (body.sizeBytes > MAX_UPLOAD_BYTES) {
      return new Response(
        JSON.stringify({ error: "file_too_large", maxBytes: MAX_UPLOAD_BYTES }),
        { status: 413, headers: { "Content-Type": "application/json" } }
      );
    }

    const objectKey = `uploads/${body.userId}/${crypto.randomUUID()}/${body.filename}`;

    // R2 presigned URL via Workers Binding (requires R2 bucket with public URL enabled)
    const presignedUrl = await env.UPLOADS.createMultipartUpload
      ? undefined // multipart has its own flow — see anti-patterns
      : undefined;

    // For single PUT presigned URL:
    const url = await env.UPLOADS.put(objectKey, null, {
      // Note: as of 2026, Workers R2 binding does not support presigned PUT URL generation
      // natively — use the S3-compatible API with an Access Key instead.
    });

    // S3-compatible presigned URL (recommended approach):
    const s3PresignedUrl = await generateR2PresignedUrl({
      bucket: "my-uploads",
      key: objectKey,
      contentType: body.contentType,
      ttlSeconds: PRESIGN_TTL_SECONDS,
      accountId: "your-account-id", // from env
      accessKeyId: "your-access-key-id", // from env secret
      secretAccessKey: "your-secret-access-key", // from env secret
    });

    // Record pending upload in D1
    await env.DB.prepare(
      `INSERT INTO uploads (object_key, user_id, filename, content_type, size_bytes, status, created_at)
       VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'))`
    )
      .bind(objectKey, body.userId, body.filename, body.contentType, body.sizeBytes)
      .run();

    return Response.json({ presignedUrl: s3PresignedUrl, objectKey });
  },
};

async function generateR2PresignedUrl(opts: {
  bucket: string;
  key: string;
  contentType: string;
  ttlSeconds: number;
  accountId: string;
  accessKeyId: string;
  secretAccessKey: string;
}): Promise<string> {
  // Uses AWS Signature V4 to produce a presigned PUT URL against R2's S3-compat endpoint.
  const endpoint = `https://${opts.accountId}.r2.cloudflarestorage.com`;
  const expiresAt = Math.floor(Date.now() / 1000) + opts.ttlSeconds;

  // Full sigV4 implementation omitted for brevity — use `aws4fetch` package in Workers.
  // npm install aws4fetch
  const { AwsClient } = await import("aws4fetch");
  const aws = new AwsClient({
    accessKeyId: opts.accessKeyId,
    secretAccessKey: opts.secretAccessKey,
    region: "auto",
    service: "s3",
  });

  const requestUrl = `${endpoint}/${opts.bucket}/${opts.key}`;
  const signed = await aws.sign(
    new Request(requestUrl, { method: "PUT" }),
    { aws: { signQuery: true }, expiresIn: opts.ttlSeconds }
  );

  return signed.url;
}
```

---

## Mobile Client: Pick File and Upload

```typescript
// src/services/fileUpload.ts
import { FilePicker, PickedFile } from "@capawesome-team/capacitor-file-picker";
import { Filesystem, Encoding } from "@capacitor/filesystem";

const WORKERS_BASE = "https://api.example.com";

export interface UploadResult {
  objectKey: string;
  filename: string;
  sizeBytes: number;
}

export async function pickAndUploadFile(
  userId: string,
  allowedTypes?: string[]
): Promise<UploadResult> {
  // Step 1: Open native file picker
  const result = await FilePicker.pickFiles({
    types: allowedTypes ?? ["application/pdf", "image/*", "video/*"],
    multiple: false,
    readData: false, // do NOT read into base64 — use URI path instead
  });

  const file: PickedFile = result.files[0];

  if (!file.path) {
    throw new Error("File picker did not return a local path");
  }

  // Step 2: Request presigned URL from Workers
  const presignResp = await fetch(`${WORKERS_BASE}/upload/presign`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${await getAccessToken()}` },
    body: JSON.stringify({
      filename: file.name,
      contentType: file.mimeType ?? "application/octet-stream",
      sizeBytes: file.size ?? 0,
      userId,
    }),
  });

  if (!presignResp.ok) {
    const err = await presignResp.json<{ error: string }>();
    throw new Error(`Presign failed: ${err.error}`);
  }

  const { presignedUrl, objectKey } = await presignResp.json<{
    presignedUrl: string;
    objectKey: string;
  }>();

  // Step 3: Stream file directly to R2
  // On native, file.path is a file:// URI usable with fetch directly in Capacitor's HTTP layer.
  const fileBlob = await pathToBlob(file.path, file.mimeType ?? "application/octet-stream");

  const uploadResp = await fetch(presignedUrl, {
    method: "PUT",
    headers: { "Content-Type": file.mimeType ?? "application/octet-stream" },
    body: fileBlob,
  });

  if (!uploadResp.ok) {
    throw new Error(`R2 upload failed: ${uploadResp.status}`);
  }

  // Step 4: Confirm with Workers so D1 status is updated
  await fetch(`${WORKERS_BASE}/upload/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${await getAccessToken()}` },
    body: JSON.stringify({ objectKey }),
  });

  return { objectKey, filename: file.name, sizeBytes: file.size ?? 0 };
}

async function pathToBlob(path: string, mimeType: string): Promise<Blob> {
  // Capacitor Filesystem.readFile works for small files (<50 MB).
  // For large files prefer the native HTTP plugin to stream directly.
  const { data } = await Filesystem.readFile({ path });
  // data is base64 string when no encoding is set
  const binary = atob(data as string);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mimeType });
}

async function getAccessToken(): Promise<string> {
  // Retrieve stored JWT / refresh if expired
  return "...";
}
```

---

## Upload Progress with @capacitor-community/http

For large files, swap the `fetch` upload call for `@capacitor-community/http` which supports
native progress events:

```typescript
import { Http } from "@capacitor-community/http";

const uploadWithProgress = async (
  presignedUrl: string,
  filePath: string,
  mimeType: string,
  onProgress: (pct: number) => void
) => {
  return Http.uploadFile({
    url: presignedUrl,
    name: "file",
    filePath,
    fileDirectory: undefined,
    method: "PUT",
    headers: { "Content-Type": mimeType },
  });
  // Progress events not yet in stable HTTP plugin as of mid-2026;
  // use React Native fetch streaming or background URLSession for iOS instead.
};
```

---

## Anti-patterns

- **Reading files into base64 before upload.** For files above ~10 MB this exhausts the JS heap
  on low-end Android devices. Always prefer `readData: false` in `pickFiles` and stream via URI.
- **Routing the binary through Workers.** Workers have a 100 MB request body limit and a 30-second
  CPU time limit. Use presigned URLs so R2 accepts the body directly.
- **Single presigned URL for files >5 GB.** R2 single-object PUT cap is 5 GB. Use
  `createMultipartUpload` on the R2 binding for large files and issue per-part presigned URLs.
- **Forgetting to confirm the upload.** Without a confirm step the D1 row stays `pending`
  indefinitely. Add a D1 cleanup job or use an R2 event notification to flip the status.
- **Exposing the R2 Access Key ID and Secret in the mobile bundle.** Always generate presigned
  URLs server-side inside Workers, never in the app.

---

## Gotchas

- On Android, `file.path` from the picker is a `content://` URI, not `file://`. Capacitor's
  Filesystem plugin resolves it, but some direct-fetch implementations do not. Test on a physical
  device with a file from Google Drive vs. local storage — paths differ.
- iOS will invalidate the security-scoped bookmark granted by UIDocumentPickerViewController
  when your app goes to background mid-upload. Use a background URLSession (Capacitor Background
  Runner or native module) for uploads expected to exceed 30 seconds.
- R2 presigned PUT URLs do not support `Transfer-Encoding: chunked`. Set an exact
  `Content-Length` header or the upload will be rejected.
- MIME type detection from the picker is unreliable on Android — cross-check with file extension
  as a fallback before sending `contentType` to Workers.

---

## Verification

```bash
# Confirm object landed in R2
wrangler r2 object get my-uploads "uploads/<userId>/<uuid>/<filename>" --pipe | file -

# Check D1 for confirmed status
wrangler d1 execute my-db --command \
  "SELECT object_key, status FROM uploads WHERE user_id='<userId>' ORDER BY created_at DESC LIMIT 5"
```

---

## Related

- `capacitor-workers-camera-r2-upload.md` — camera frame upload variant
- `react-native-r2-multipart-upload-progress.md` — multipart upload with progress
- `cloudflare-r2-presigned-url-mobile-clock-drift.md` — clock skew issues with presigned URLs
- `mobile-app-size-optimization.md` — avoiding base64 memory bloat

---

## Sources

- https://capawesome.io/plugins/file-picker/
- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://capacitorjs.com/docs/apis/filesystem
