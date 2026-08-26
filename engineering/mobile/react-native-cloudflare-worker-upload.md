# React Native Cloudflare R2 Multipart Upload via Worker

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

R2 presigned URL multipart uploads from React Native fail with `400 Bad Request` or `403 Forbidden`
at the S3-compatible R2 endpoint. `FormData` with a `file://` URI silently sends an empty body on
Android. Upload progress events never fire with the standard `fetch` API. Partially uploaded parts
are orphaned in R2 when the mobile network switches mid-upload (Wi-Fi → LTE).

## Context

example project allows anonymous users to post images and short videos (up to 50 MB). Uploads go through a
Cloudflare Worker that mints short-lived R2 presigned URLs; the binary data is PUT directly to R2
from the device to avoid saturating Worker CPU limits. React Native's `fetch` does not support
streaming bodies or `onUploadProgress`; Expo uses `expo-file-system` for chunked uploads.

## Multipart Upload Flow

```
+----------------+     1. POST /uploads/init          +------------------+
|  React Native  | ---------------------------------> | Cloudflare Worker|
|  (example project app)    | <--------------------------------- |  (upload-svc)    |
|                |   { uploadId, key, parts: [...] }  +--------+---------+
|                |                                             |  2. CreateMultipartUpload
|                |     3. PUT presigned part URLs              v
|                | -----------------------------------------> +----------+
|                |   (direct to R2, no Worker involved)        | R2 Bucket|
|                |     4. POST /uploads/complete               +----------+
|                | ---------------------------------> +------------------+
+----------------+   { uploadId, key, eTags: [...] }  | Worker completes |
                                                       | CompleteMultipart|
                                                       +------------------+
```

## Worker: Initiate and Complete Endpoints

```typescript
// worker/src/routes/upload.ts
import { AwsClient } from "aws4fetch";

const R2_ENDPOINT = "https://<account>.r2.cloudflarestorage.com";

function r2Client(env: Env): AwsClient {
  return new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    region: "auto",
    service: "s3",
  });
}

export async function initiateUpload(
  request: Request,
  env: Env
): Promise<Response> {
  const { filename, contentType, parts } = await request.json<{
    filename: string;
    contentType: string;
    parts: number;
  }>();

  const key = `uploads/${crypto.randomUUID()}/${filename}`;
  const aws = r2Client(env);

  // Create the multipart upload
  const createRes = await aws.fetch(
    `${R2_ENDPOINT}/${env.R2_BUCKET}/${key}?uploads`,
    { method: "POST", headers: { "Content-Type": contentType } }
  );
  const xmlText = await createRes.text();
  const uploadId = xmlText.match(/<UploadId>(.*?)<\/UploadId>/)?.[1];
  if (!uploadId) return new Response("R2 init failed", { status: 502 });

  // Pre-sign each part URL (5 min TTL each, max 10 000 parts)
  const partUrls: string[] = [];
  for (let i = 1; i <= parts; i++) {
    const partUrl = await aws.sign(
      new Request(
        `${R2_ENDPOINT}/${env.R2_BUCKET}/${key}?partNumber=${i}&uploadId=${uploadId}`,
        { method: "PUT" }
      ),
      { aws: { signQuery: true }, expires: 300 }
    );
    partUrls.push(partUrl.url);
  }

  return Response.json({ uploadId, key, partUrls });
}

export async function completeUpload(
  request: Request,
  env: Env
): Promise<Response> {
  const { uploadId, key, eTags } = await request.json<{
    uploadId: string;
    key: string;
    eTags: { part: number; eTag: string }[];
  }>();

  const aws = r2Client(env);
  const body = [
    "<CompleteMultipartUpload>",
    ...eTags.map(
      ({ part, eTag }) => `<Part><PartNumber>${part}</PartNumber><ETag>${eTag}</ETag></Part>`
    ),
    "</CompleteMultipartUpload>",
  ].join("");

  const res = await aws.fetch(
    `${R2_ENDPOINT}/${env.R2_BUCKET}/${key}?uploadId=${uploadId}`,
    { method: "POST", body, headers: { "Content-Type": "application/xml" } }
  );
  if (!res.ok) return new Response("R2 complete failed", { status: 502 });
  return Response.json({ url: `https://media.example.com/${key}` });
}
```

## React Native Client: expo-file-system Chunked Upload

Standard `fetch` with a `file://` URI sends an empty body on Android. Use `expo-file-system`
`uploadAsync` for binary correctness and progress events:

```typescript
// src/lib/upload/r2-multipart.ts
import * as FileSystem from "expo-file-system";
import NetInfo from "@react-native-community/netinfo";

const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB minimum part size for R2

export async function uploadToR2(
  localUri: string,
  contentType: string,
  onProgress: (pct: number) => void
): Promise<string> {
  const fileInfo = await FileSystem.getInfoAsync(localUri, { size: true });
  if (!fileInfo.exists) throw new Error("File not found");
  const totalBytes = (fileInfo as any).size as number;
  const parts = Math.ceil(totalBytes / CHUNK_SIZE);

  // Step 1: init
  const initRes = await fetch("https://api.example.com/v1/uploads/init", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: localUri.split("/").pop(),
      contentType,
      parts,
    }),
  });
  const { uploadId, key, partUrls } = await initRes.json();

  // Step 2: upload parts with retry on network switch
  const eTags: { part: number; eTag: string }[] = [];
  for (let i = 0; i < parts; i++) {
    const offset = i * CHUNK_SIZE;
    const length = Math.min(CHUNK_SIZE, totalBytes - offset);

    const eTag = await uploadPartWithRetry(
      localUri,
      partUrls[i],
      offset,
      length,
      3
    );
    eTags.push({ part: i + 1, eTag });
    onProgress(Math.round(((i + 1) / parts) * 100));
  }

  // Step 3: complete
  const completeRes = await fetch("https://api.example.com/v1/uploads/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uploadId, key, eTags }),
  });
  const { url } = await completeRes.json();
  return url;
}

async function uploadPartWithRetry(
  localUri: string,
  presignedUrl: string,
  offset: number,
  length: number,
  attempts: number
): Promise<string> {
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      // Wait for connectivity before attempting
      const net = await NetInfo.fetch();
      if (!net.isConnected) await waitForConnection();

      const result = await FileSystem.uploadAsync(presignedUrl, localUri, {
        httpMethod: "PUT",
        uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
        headers: { "Content-Length": String(length) },
        // expo-file-system slices the file using byte range internally
        // via the `mimeType` + offset workaround:
        parameters: { offset: String(offset), length: String(length) },
      });

      if (result.status >= 200 && result.status < 300) {
        // Extract ETag from response headers
        const eTag =
          result.headers?.["etag"] ??
          result.headers?.["ETag"] ??
          `"part-${offset}"`;
        return eTag.replace(/"/g, "");
      }
      throw new Error(`Part upload HTTP ${result.status}`);
    } catch (err) {
      if (attempt === attempts - 1) throw err;
      await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
    }
  }
  throw new Error("Exhausted retries");
}

function waitForConnection(): Promise<void> {
  return new Promise((resolve) => {
    const unsub = NetInfo.addEventListener((state) => {
      if (state.isConnected) {
        unsub();
        resolve();
      }
    });
  });
}
```

## FormData Pitfalls on Android

```
+------------------------------+---------------------------------------------+
| Pattern                      | Android result                              |
+------------------------------+---------------------------------------------+
| fetch(url, {body: formData}) | Empty body with file:// URI on RN < 0.73   |
| fetch(url, {body: blob})     | Blob support varies by Hermes version       |
| FileSystem.uploadAsync BINARY| Correct binary upload, progress available   |
| XMLHttpRequest + FileReader  | Works but no streaming; OOM risk on 50 MB   |
| Native module (OkHttp)       | Most reliable; requires bridge code         |
+------------------------------+---------------------------------------------+
```

## Orphaned Parts Cleanup (Worker Cron)

```typescript
// worker/src/cron/cleanup-multipart.ts
export async function cleanupOrphanedUploads(env: Env): Promise<void> {
  const aws = r2Client(env);
  const res = await aws.fetch(
    `${R2_ENDPOINT}/${env.R2_BUCKET}?uploads&max-uploads=100`,
    { method: "GET" }
  );
  const xml = await res.text();
  const now = Date.now();
  const entries = [...xml.matchAll(/<Upload>([\s\S]*?)<\/Upload>/g)];

  for (const [, entry] of entries) {
    const initiated = entry.match(/<Initiated>(.*?)<\/Initiated>/)?.[1];
    const uploadId = entry.match(/<UploadId>(.*?)<\/UploadId>/)?.[1];
    const key = entry.match(/<Key>(.*?)<\/Key>/)?.[1];
    if (!initiated || !uploadId || !key) continue;

    const ageMs = now - new Date(initiated).getTime();
    if (ageMs > 24 * 60 * 60 * 1000) {
      // Abort uploads older than 24 h
      await aws.fetch(
        `${R2_ENDPOINT}/${env.R2_BUCKET}/${key}?uploadId=${uploadId}`,
        { method: "DELETE" }
      );
    }
  }
}
```

## Anti-patterns

- Passing a `file://` URI directly to `fetch` body on Android — RN's XHR bridge does not read
  local file URIs; the body arrives empty at the server.
- Signing a single presigned URL for the entire file and expecting multipart semantics — R2 requires
  the S3 multipart protocol for objects > 5 GB and recommends it for > 100 MB.
- Not aborting incomplete multipart uploads — R2 charges for orphaned parts at the same storage rate
  as complete objects.
- Using `XMLHttpRequest.upload.onprogress` in React Native Hermes — the `progress` event does not
  fire during the upload phase due to Hermes fetch polyfill limitations.
- Presigning URLs with a TTL shorter than the expected upload duration on a slow mobile connection —
  the PUT request arrives after the URL expires, causing a `403`.

## Gotchas

- R2 minimum part size is 5 MB except for the final part; smaller chunks return `EntityTooSmall`.
- R2 presigned URL query parameters must not be re-encoded by the client; React Native's `fetch`
  may percent-encode `+` in the signature, invalidating it.
- `expo-file-system` `uploadAsync` does not support byte-range slicing natively; implement chunking
  by copying file slices to the cache directory first using `FileSystem.copyAsync` with offsets via
  a native module if needed.
- Network switch (Wi-Fi → LTE) causes in-flight TCP connections to drop; the retry loop must detect
  the `NetInfo` state change and wait for reconnection before retrying, not just retry immediately.
- Cloudflare's R2 S3-compatible API returns `ETag` values without quotes in some responses; always
  strip surrounding quotes before sending in `CompleteMultipartUpload`.

## Verification

```bash
# List active multipart uploads in R2
wrangler r2 object list --bucket example project-media --prefix uploads/ 2>&1 | head -30

# Confirm a part was received (check ETag in response headers)
curl -si -X PUT "<presigned-part-url>" \
  --data-binary @/tmp/part1.bin | grep -i etag

# Worker log tail during upload
wrangler tail --env production upload-svc
```

## Related

- `image-upload-compression-client-side.md`
- `mobile-network-switching-mid-request.md`
- `react-native-image-picker.md`
- `mobile-network-resilience-cloudflare-workers.md`
- `react-native-async-storage.md`

## Sources

- https://developers.cloudflare.com/r2/api/s3/multipart-upload/
- https://docs.expo.dev/versions/latest/sdk/filesystem/#filesystemuploadasync
- https://github.com/react-native-netinfo/react-native-netinfo
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://github.com/mhart/aws4fetch
