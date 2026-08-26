# Expo Camera R2 Upload Compression Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Users capture photos via Expo Camera and need them stored in Cloudflare R2 with minimal
bandwidth usage and fast perceived upload speed. Naive approaches upload raw camera output
(10–50 MB per photo), time out on cellular, and burn through R2 storage budgets.
Multipart upload through a Workers signing proxy plus client-side compression solves all three.

## Context

`expo-camera` and `expo-image-manipulator` run on the Hermes JS thread. Compression must
finish before the upload handshake starts. R2 multipart upload (minimum part size 5 MB) lets
the device stream compressed chunks without buffering the whole file in memory. A Cloudflare
Worker acts as the signing proxy and issues part upload acknowledgements so the device never
holds long-lived R2 credentials.

---

## 1. Camera Capture with expo-camera

```tsx
// components/CaptureButton.tsx
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImageManipulator from 'expo-image-manipulator';
import { useRef } from 'react';
import { Pressable, Text } from 'react-native';

interface Props { onCapture: (uri: string) => void }

export function CaptureButton({ onCapture }: Props) {
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();

  if (!permission?.granted) {
    return <Pressable onPress={requestPermission}><Text>Allow Camera</Text></Pressable>;
  }

  const capture = async () => {
    const photo = await cameraRef.current?.takePictureAsync({
      quality: 1,
      skipProcessing: true,   // get raw JPEG before any system cropping
    });
    if (!photo) return;

    const compressed = await ImageManipulator.manipulateAsync(
      photo.uri,
      [{ resize: { width: 1920 } }],
      { compress: 0.82, format: ImageManipulator.SaveFormat.JPEG }
    );
    onCapture(compressed.uri);
  };

  return (
    <CameraView ref={cameraRef} style={{ flex: 1 }}>
      <Pressable onPress={capture} style={{ alignSelf: 'center', marginBottom: 40 }}>
        <Text style={{ color: '#fff', fontSize: 18 }}>Capture</Text>
      </Pressable>
    </CameraView>
  );
}
```

---

## 2. Workers Multipart Signing Proxy

```typescript
// worker/src/r2-upload.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/upload/init' && req.method === 'POST') {
      const { filename } = await req.json<{ filename: string }>();
      const key = `expo/${crypto.randomUUID()}/${filename}`;
      const upload = await env.BUCKET.createMultipartUpload(key);
      return Response.json({ key, uploadId: upload.uploadId });
    }

    if (url.pathname === '/upload/part' && req.method === 'PUT') {
      const key = url.searchParams.get('key')!;
      const uploadId = url.searchParams.get('uploadId')!;
      const part = parseInt(url.searchParams.get('part')!, 10);
      const mu = env.BUCKET.resumeMultipartUpload(key, uploadId);
      const uploaded = await mu.uploadPart(part, req.body!);
      return Response.json({ etag: uploaded.etag, partNumber: part });
    }

    if (url.pathname === '/upload/complete' && req.method === 'POST') {
      const { key, uploadId, parts } = await req.json<{
        key: string;
        uploadId: string;
        parts: Array<{ partNumber: number; etag: string }>;
      }>();
      const mu = env.BUCKET.resumeMultipartUpload(key, uploadId);
      await mu.complete(parts);
      return Response.json({ cdnUrl: `https://cdn.example.com/${key}` });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## 3. Client Multipart Upload Loop

```typescript
// lib/r2Uploader.ts
import * as FileSystem from 'expo-file-system';

const PART_SIZE = 5 * 1024 * 1024; // 5 MB — R2 minimum for all parts except the last
const WORKER_BASE = 'https://upload.example.com';

export async function uploadToR2(
  uri: string,
  onProgress?: (ratio: number) => void
): Promise<string> {
  const info = await FileSystem.getInfoAsync(uri, { size: true }) as FileSystem.FileInfo & { size: number };
  const totalSize = info.size;
  const partCount = Math.ceil(totalSize / PART_SIZE);

  // 1 — initiate
  const { key, uploadId } = await fetch(`${WORKER_BASE}/upload/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: 'photo.jpg' }),
  }).then(r => r.json<{ key: string; uploadId: string }>());

  // 2 — upload parts
  const eTags: Array<{ partNumber: number; etag: string }> = [];
  for (let i = 0; i < partCount; i++) {
    const start = i * PART_SIZE;
    const length = Math.min(PART_SIZE, totalSize - start);
    const chunk = await FileSystem.readAsStringAsync(uri, {
      encoding: FileSystem.EncodingType.Base64,
      position: start,
      length,
    });
    const bytes = Uint8Array.from(atob(chunk), c => c.charCodeAt(0));
    const res = await fetch(
      `${WORKER_BASE}/upload/part?key=${key}&uploadId=${uploadId}&part=${i + 1}`,
      { method: 'PUT', body: bytes }
    );
    const { etag } = await res.json<{ etag: string }>();
    eTags.push({ partNumber: i + 1, etag });
    onProgress?.((i + 1) / partCount);
  }

  // 3 — complete
  const { cdnUrl } = await fetch(`${WORKER_BASE}/upload/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, uploadId, parts: eTags }),
  }).then(r => r.json<{ cdnUrl: string }>());

  return cdnUrl;
}
```

---

## 4. Upload Progress Hook

```tsx
// hooks/useUpload.ts
import { useState, useCallback } from 'react';
import { uploadToR2 } from '../lib/r2Uploader';

export function useUpload() {
  const [progress, setProgress] = useState(0);
  const [cdnUrl, setCdnUrl] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const upload = useCallback(async (uri: string) => {
    setProgress(0);
    setError(null);
    try {
      const url = await uploadToR2(uri, p => setProgress(p));
      setCdnUrl(url);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    }
  }, []);

  return { progress, cdnUrl, error, upload };
}
```

---

## 5. D1 Metadata Storage After Completion

```typescript
// worker/src/r2-upload.ts (complete handler, extended)
async function recordUpload(env: Env, key: string, userId: string, sizeBytes: number) {
  await env.DB.prepare(
    `INSERT INTO uploads (id, user_id, r2_key, size_bytes, created_at)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(crypto.randomUUID(), userId, key, sizeBytes, new Date().toISOString())
    .run();
}
```

---

## Anti-patterns

- Uploading raw HEIC directly to R2 — convert to JPEG first; HEIC rendering in web-facing R2 buckets is inconsistent.
- Single-PUT for files over 5 MB — cellular connections drop mid-stream; multipart lets you resume from the last completed part.
- Storing R2 credentials on the device — use the Workers proxy; credential revocation is per-Worker, not per-device.
- Compressing inside a render function — call `ImageManipulator.manipulateAsync` once and cache the output URI in `useRef`.

## Gotchas

- `expo-image-manipulator` does not process video; use `expo-video-thumbnails` for poster frames and a separate transcode step for video.
- `FileSystem.readAsStringAsync` with `position`/`length` is iOS-only before Expo SDK 51 — on Android, fetch the file with a `Range` header instead.
- R2 requires every part except the last to be ≥ 5 MB; validate `partCount` math server-side before issuing the first `uploadPart` call.
- `createMultipartUpload` does not auto-expire — add a Workers Cron Trigger to abort uploads older than 24 hours.

## Verification

```bash
# Confirm the init endpoint returns a key and uploadId
curl -X POST https://upload.example.com/upload/init \
  -H "Content-Type: application/json" -d '{"filename":"test.jpg"}'

# List recent objects in the bucket
wrangler r2 object list expo-media --prefix expo/

# Check D1 upload log
wrangler d1 execute DB --command \
  "SELECT * FROM uploads ORDER BY created_at DESC LIMIT 5;"
```

## Related

- `capacitor-workers-camera-r2-upload.md`
- `react-native-r2-multipart-upload-progress.md`
- `image-upload-compression-client-side.md`
- `expo-eas-build-cloudflare-workers-secrets.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-multipart-usage/
- https://docs.expo.dev/versions/latest/sdk/camera/
- https://docs.expo.dev/versions/latest/sdk/imagemanipulator/
- https://docs.expo.dev/versions/latest/sdk/filesystem/
