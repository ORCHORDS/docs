# Capacitor Workers Camera R2 Upload

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

A Capacitor hybrid app lets users photograph items or documents and needs to store them in
Cloudflare R2. Direct browser `fetch` to R2 public endpoints exposes credentials; uploading
via a Workers presigned-URL relay keeps secrets server-side, compresses images before transfer,
and tracks upload metadata in D1. Progress reporting must work on both iOS and Android native
WebView.

## Context

The flow is: Capacitor Camera plugin captures an image → JS layer requests a presigned upload
URL from Workers → app `PUT`s the file directly to R2 using the presigned URL → Workers
receives the R2 completion webhook (or polling) and writes metadata to D1. CORS is controlled
by Workers, not R2 public access, so the bucket stays private.

---

## 1. Workers Presigned URL Generator

```typescript
// worker/src/presign.ts
import { AwsClient } from "aws4fetch";

export interface PresignRequest {
  filename: string;
  contentType: string;
  sizeBytes: number;
}

export interface PresignResponse {
  uploadUrl: string;
  key: string;
  expiresAt: number; // epoch ms
}

export async function generatePresignedUpload(
  req: Request,
  env: Env
): Promise<Response> {
  const body = await req.json<PresignRequest>();
  if (body.sizeBytes > 50 * 1024 * 1024) {
    return Response.json({ error: "File too large (max 50 MB)" }, { status: 413 });
  }
  const key = `uploads/${crypto.randomUUID()}/${body.filename}`;
  const aws = new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    region: "auto",
    service: "s3",
  });
  const expiresIn = 300; // 5 minutes
  const r2Url = `https://${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${env.R2_BUCKET}/${key}`;
  const signed = await aws.sign(
    new Request(r2Url, {
      method: "PUT",
      headers: {
        "Content-Type": body.contentType,
        "Content-Length": String(body.sizeBytes),
      },
    }),
    { aws: { signQuery: true }, expiresIn }
  );

  return Response.json({
    uploadUrl: signed.url,
    key,
    expiresAt: Date.now() + expiresIn * 1000,
  } satisfies PresignResponse);
}
```

---

## 2. Workers Metadata Registration After Upload

```typescript
// worker/src/register.ts
export async function registerUpload(req: Request, env: Env): Promise<Response> {
  const { key, userId, caption } = await req.json<{
    key: string;
    userId: string;
    caption?: string;
  }>();

  // Verify the object exists in R2 before recording it
  const obj = await env.BUCKET.head(key);
  if (!obj) {
    return Response.json({ error: "Object not found in R2" }, { status: 404 });
  }

  await env.DB.prepare(
    `INSERT INTO uploads (id, user_id, r2_key, size_bytes, content_type, caption, created_at)
     VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`
  )
    .bind(
      crypto.randomUUID(),
      userId,
      key,
      obj.size,
      obj.httpMetadata?.contentType ?? "application/octet-stream",
      caption ?? null
    )
    .run();

  const publicUrl = `https://${env.R2_PUBLIC_DOMAIN}/${key}`;
  return Response.json({ ok: true, url: publicUrl });
}
```

---

## 3. Capacitor TypeScript Upload Service

```typescript
// src/services/camera-upload.service.ts
import { Camera, CameraResultType, CameraSource } from "@capacitor/camera";
import { Filesystem, Directory } from "@capacitor/filesystem";

const WORKERS_BASE = import.meta.env.VITE_WORKERS_BASE_URL;

export async function captureAndUpload(
  userId: string,
  caption?: string
): Promise<string> {
  // 1. Capture photo
  const photo = await Camera.getPhoto({
    quality: 80,
    allowEditing: false,
    resultType: CameraResultType.Base64,
    source: CameraSource.Camera,
  });

  if (!photo.base64String) throw new Error("No image data");

  // 2. Convert base64 to Blob
  const byteChars = atob(photo.base64String);
  const byteArr = new Uint8Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) byteArr[i] = byteChars.charCodeAt(i);
  const blob = new Blob([byteArr], { type: `image/${photo.format}` });

  // 3. Request presigned URL
  const presignRes = await fetch(`${WORKERS_BASE}/api/presign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: `capture.${photo.format}`,
      contentType: `image/${photo.format}`,
      sizeBytes: blob.size,
    }),
  });
  if (!presignRes.ok) throw new Error("Failed to get presigned URL");
  const { uploadUrl, key } = await presignRes.json<{
    uploadUrl: string;
    key: string;
    expiresAt: number;
  }>();

  // 4. PUT directly to R2 via presigned URL
  const uploadRes = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": `image/${photo.format}` },
    body: blob,
  });
  if (!uploadRes.ok) throw new Error(`R2 upload failed: ${uploadRes.status}`);

  // 5. Register metadata via Workers
  const registerRes = await fetch(`${WORKERS_BASE}/api/uploads/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, userId, caption }),
  });
  if (!registerRes.ok) throw new Error("Metadata registration failed");
  const { url } = await registerRes.json<{ ok: boolean; url: string }>();
  return url;
}
```

---

## 4. Upload Progress via XMLHttpRequest (WebView-Compatible)

```typescript
// src/services/upload-with-progress.ts
export function uploadWithProgress(
  url: string,
  blob: Blob,
  contentType: string,
  onProgress: (pct: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", contentType);
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed: ${xhr.status}`));
    });
    xhr.addEventListener("error", () => reject(new Error("Network error")));
    xhr.send(blob);
  });
}
```

---

## 5. Workers CORS Configuration for R2 Upload Relay

```typescript
// worker/src/cors.ts
const ALLOWED_ORIGINS = [
  "capacitor://localhost",
  "http://localhost",
  "https://app.example.com",
];

export function corsHeaders(origin: string | null): Record<string, string> {
  const allowed = origin && ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}
```

---

## Anti-patterns

- **Uploading to R2 via Workers as a proxy** — streaming a 10 MB photo through Workers costs
  CPU time and egress; always use presigned URLs so the client PUTs directly to R2.
- **Storing base64 in D1** — only store the R2 object key and metadata in D1; the binary stays
  in R2 where it belongs and is served cheaply.
- **No expiry on presigned URLs** — a presigned URL with no expiry is a permanent write
  credential; always set `expiresIn` to 300 seconds or less.
- **Using `CameraResultType.Uri` on Android** — file URIs are sandboxed; use `Base64` or
  `DataUrl` to get transferable bytes that work across WebView boundaries.

## Gotchas

- **`capacitor://localhost` CORS origin on iOS** — iOS WKWebView uses `capacitor://localhost`
  as the request origin; include it explicitly in your Workers CORS allow-list.
- **Camera permissions on Android 14+** — the `READ_MEDIA_IMAGES` permission is required
  separately from camera for gallery access; the Capacitor Camera plugin requests both but
  verify in the manifest.
- **R2 presigned URL region** — always use `region: "auto"` with the R2-specific endpoint
  (`*.r2.cloudflarestorage.com`); `us-east-1` will cause signature mismatch errors.
- **Large images on low-memory devices** — `quality: 80` in `Camera.getPhoto` compresses on
  the native side; do not re-encode the base64 in JS as a second compression pass will degrade
  quality without reducing size meaningfully.

## Verification

```bash
# Test presign endpoint
curl -X POST https://api.example.com/api/presign \
  -H 'Content-Type: application/json' \
  -d '{"filename":"test.jpg","contentType":"image/jpeg","sizeBytes":1024}'

# Upload a test file to the returned URL
UPLOAD_URL=$(curl -s ... | jq -r '.uploadUrl')
curl -X PUT "$UPLOAD_URL" -H 'Content-Type: image/jpeg' --data-binary @test.jpg

# Confirm object landed in R2
wrangler r2 object get BUCKET_NAME uploads/<uuid>/test.jpg --file /tmp/out.jpg

# Verify D1 metadata row after registration
wrangler d1 execute DB --command "SELECT * FROM uploads ORDER BY created_at DESC LIMIT 1"
```

## Related

- `capacitor-r2-live-updates.md`
- `capacitor-http-plugin-workers-cors.md`
- `react-native-r2-multipart-upload-progress.md`
- `ios-background-upload-session-r2-workers.md`
- `image-upload-compression-client-side.md`

## Sources

- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://capacitorjs.com/docs/apis/camera
- https://developers.cloudflare.com/r2/buckets/cors/
- https://developers.cloudflare.com/workers/runtime-apis/r2/
