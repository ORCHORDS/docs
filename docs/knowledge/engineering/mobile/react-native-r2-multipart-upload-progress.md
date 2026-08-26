# React Native Image Upload to R2 with Multipart + Progress Tracking

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project (example.com) users upload profile images, audio recordings, and attachments from their phones. Uploads over ~5 MB via a single `fetch`/`PUT` request to a Cloudflare R2 presigned URL frequently time out on mobile networks, drop mid-upload with no recovery path, and provide no progress feedback. The S3-compatible multipart upload API supported by R2 solves all three problems but requires a Workers orchestration layer and careful React Native `XMLHttpRequest` usage to surface progress events.

## Context

Cloudflare R2 supports the S3 multipart upload protocol:
- **Initiate**: `POST /{bucket}/{key}?uploads` → returns `UploadId`
- **Upload part**: `PUT /{bucket}/{key}?partNumber={n}&uploadId={id}` (minimum 5 MB per part except last)
- **Complete**: `POST /{bucket}/{key}?uploadId={id}` with the ETag list

Because R2's public bucket URL does not accept direct S3 API calls from mobile (CORS, auth), a **Cloudflare Worker acts as the orchestrator**: it issues part-level presigned URLs for the mobile client and handles the final `CompleteMultipartUpload` call. The mobile client uploads parts directly to R2 using the presigned URLs (bypassing the Worker for the actual data transfer) and reports progress per-part.

---

## 1. Worker: Multipart Upload Orchestration

```ts
// workers/upload/src/index.ts
import { Hono } from 'hono'
import { S3Client, CreateMultipartUploadCommand, UploadPartCommand,
         CompleteMultipartUploadCommand, AbortMultipartUploadCommand }
  from '@aws-sdk/client-s3'
import { getSignedUrl } from '@aws-sdk/s3-request-presigner'

const app = new Hono<{ Bindings: Env }>()

function getS3Client(env: Env) {
  return new S3Client({
    region: 'auto',
    endpoint: `https://${env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: env.R2_ACCESS_KEY_ID,
      secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    },
  })
}

const PART_SIZE = 5 * 1024 * 1024 // 5 MB minimum (R2 requirement)
const URL_EXPIRY = 3600             // 1 hour in seconds

// POST /upload/initiate
// Body: { filename, contentType, sizeBytes }
// Returns: { uploadId, key, partUrls: [{ partNumber, url }], partSize }
app.post('/upload/initiate', async (c) => {
  const { filename, contentType, sizeBytes } = await c.req.json<{
    filename: string
    contentType: string
    sizeBytes: number
  }>()

  const userId = c.get('userId') as string  // set by auth middleware
  const key = `uploads/${userId}/${Date.now()}-${filename}`

  const s3 = getS3Client(c.env)

  // Create the multipart upload session
  const create = await s3.send(new CreateMultipartUploadCommand({
    Bucket: c.env.R2_BUCKET_NAME,
    Key: key,
    ContentType: contentType,
    Metadata: { 'uploaded-by': userId },
  }))

  const uploadId = create.UploadId!
  const partCount = Math.ceil(sizeBytes / PART_SIZE)

  // Pre-sign all part upload URLs
  const partUrls = await Promise.all(
    Array.from({ length: partCount }, (_, i) => i + 1).map(async (partNumber) => {
      const url = await getSignedUrl(
        s3,
        new UploadPartCommand({
          Bucket: c.env.R2_BUCKET_NAME,
          Key: key,
          UploadId: uploadId,
          PartNumber: partNumber,
        }),
        { expiresIn: URL_EXPIRY }
      )
      return { partNumber, url }
    })
  )

  // Track upload session in KV (for abort / resume support)
  await c.env.UPLOAD_KV.put(
    `upload:${uploadId}`,
    JSON.stringify({ key, userId, partCount, createdAt: Date.now() }),
    { expirationTtl: 86400 } // 24h
  )

  return c.json({ uploadId, key, partUrls, partSize: PART_SIZE })
})

// POST /upload/complete
// Body: { uploadId, key, parts: [{ partNumber, etag }] }
app.post('/upload/complete', async (c) => {
  const { uploadId, key, parts } = await c.req.json<{
    uploadId: string
    key: string
    parts: { partNumber: number; etag: string }[]
  }>()

  const s3 = getS3Client(c.env)
  const result = await s3.send(new CompleteMultipartUploadCommand({
    Bucket: c.env.R2_BUCKET_NAME,
    Key: key,
    UploadId: uploadId,
    MultipartUpload: {
      Parts: parts.map(p => ({ PartNumber: p.partNumber, ETag: p.etag })),
    },
  }))

  await c.env.UPLOAD_KV.delete(`upload:${uploadId}`)

  return c.json({ location: result.Location, key })
})

// POST /upload/abort
app.post('/upload/abort', async (c) => {
  const { uploadId, key } = await c.req.json<{ uploadId: string; key: string }>()
  const s3 = getS3Client(c.env)
  await s3.send(new AbortMultipartUploadCommand({
    Bucket: c.env.R2_BUCKET_NAME, Key: key, UploadId: uploadId,
  }))
  await c.env.UPLOAD_KV.delete(`upload:${uploadId}`)
  return c.json({ aborted: true })
})

export default app
```

---

## 2. React Native: Multipart Upload with Per-Part Progress

`fetch` does not expose upload progress in React Native. Use `XMLHttpRequest` for each part:

```ts
// src/uploads/multipartUpload.ts
import * as FileSystem from 'expo-file-system'

interface UploadPart { partNumber: number; etag: string }
interface PartUrl    { partNumber: number; url: string }

async function uploadPart(
  url: string,
  fileUri: string,
  offset: number,
  size: number,
  partNumber: number,
  onProgress: (partNumber: number, loaded: number, total: number) => void
): Promise<UploadPart> {
  // Read the specific byte range for this part
  const base64Chunk = await FileSystem.readAsStringAsync(fileUri, {
    encoding: FileSystem.EncodingType.Base64,
    position: offset,
    length: size,
  })

  const binaryStr = atob(base64Chunk)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url, true)
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(partNumber, e.loaded, e.total)
    }

    xhr.onload = () => {
      if (xhr.status === 200) {
        const etag = xhr.getResponseHeader('ETag') ?? ''
        resolve({ partNumber, etag: etag.replace(/"/g, '') })
      } else {
        reject(new Error(`Part ${partNumber} upload failed: HTTP ${xhr.status}`))
      }
    }

    xhr.onerror = () => reject(new Error(`Part ${partNumber} network error`))
    xhr.ontimeout = () => reject(new Error(`Part ${partNumber} timed out`))
    xhr.timeout = 120_000 // 2 min per part

    xhr.send(bytes.buffer)
  })
}

const PART_SIZE = 5 * 1024 * 1024

export async function uploadFileToR2(
  fileUri: string,
  filename: string,
  contentType: string,
  onProgress: (percent: number) => void,
  signal?: AbortSignal
): Promise<string> {
  // Get file size
  const info = await FileSystem.getInfoAsync(fileUri, { size: true })
  if (!info.exists || !info.size) throw new Error('File not found')
  const sizeBytes = info.size

  // Initiate multipart upload via Worker
  const initRes = await fetch('https://api.example.com/upload/initiate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ filename, contentType, sizeBytes }),
    signal,
  })
  if (!initRes.ok) throw new Error(`Initiate failed: ${initRes.status}`)
  const { uploadId, key, partUrls, partSize } = await initRes.json()

  // Upload parts with progress aggregation
  const partProgress = new Map<number, number>()
  const parts: UploadPart[] = []

  const handlePartProgress = (partNumber: number, loaded: number, total: number) => {
    partProgress.set(partNumber, loaded / total)
    const totalProgress = [...partProgress.values()].reduce((a, b) => a + b, 0) / partUrls.length
    onProgress(Math.round(totalProgress * 100))
  }

  for (const { partNumber, url } of partUrls as PartUrl[]) {
    if (signal?.aborted) throw new DOMException('Upload aborted', 'AbortError')
    const offset = (partNumber - 1) * partSize
    const size = Math.min(partSize, sizeBytes - offset)
    const part = await uploadPart(url, fileUri, offset, size, partNumber, handlePartProgress)
    parts.push(part)
  }

  // Complete the upload via Worker
  const completeRes = await fetch('https://api.example.com/upload/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ uploadId, key, parts }),
    signal,
  })
  if (!completeRes.ok) throw new Error(`Complete failed: ${completeRes.status}`)
  const { key: finalKey } = await completeRes.json()
  return `https://assets.example.com/${finalKey}`
}
```

---

## 3. React Native UI: Progress Bar and Abort

```tsx
// src/components/FileUploader.tsx
import React, { useState, useRef } from 'react'
import { View, Button, Text, StyleSheet } from 'react-native'
import * as ImagePicker from 'expo-image-picker'
import { uploadFileToR2 } from '@/uploads/multipartUpload'

export function FileUploader() {
  const [progress, setProgress] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [url, setUrl] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  async function pickAndUpload() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.All,
      allowsEditing: false,
      quality: 1,
    })
    if (result.canceled) return

    const asset = result.assets[0]
    abortRef.current = new AbortController()
    setUploading(true)
    setProgress(0)
    try {
      const fileUrl = await uploadFileToR2(
        asset.uri,
        asset.fileName ?? 'upload',
        asset.mimeType ?? 'application/octet-stream',
        setProgress,
        abortRef.current.signal
      )
      setUrl(fileUrl)
    } catch (e: any) {
      if (e.name !== 'AbortError') console.error('Upload error:', e)
    } finally {
      setUploading(false)
    }
  }

  return (
    <View>
      <Button title="Pick & Upload" onPress={pickAndUpload} disabled={uploading} />
      {uploading && (
        <>
          <View style={[styles.bar, { width: `${progress}%` }]} />
          <Text>{progress}%</Text>
          <Button title="Cancel" onPress={() => abortRef.current?.abort()} />
        </>
      )}
      {url && <Text selectable>{url}</Text>}
    </View>
  )
}

const styles = StyleSheet.create({
  bar: { height: 4, backgroundColor: '#0077ff', borderRadius: 2 },
})
```

---

## 4. Wrangler Configuration

```toml
# wrangler.toml (upload worker)
name = "example project-upload"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[r2_buckets]]
binding = "R2_BUCKET"          # for direct R2 bindings (if used)
bucket_name = "example project-assets"

[vars]
CF_ACCOUNT_ID = "your-account-id"
R2_BUCKET_NAME = "example project-assets"

[[kv_namespaces]]
binding = "UPLOAD_KV"
id = "your-kv-namespace-id"
```

```bash
# Set R2 S3-compat credentials as Worker secrets
wrangler secret put R2_ACCESS_KEY_ID
wrangler secret put R2_SECRET_ACCESS_KEY
```

---

## Anti-patterns

- **Using `fetch` for part uploads** — React Native's `fetch` implementation does not fire `upload.onprogress` events. Use `XMLHttpRequest` for any upload where progress tracking is required.
- **Uploading through the Worker as a proxy** — routing the binary data through a Worker for every part defeats the purpose of presigned URLs and hits the Worker's 100 MB body size limit (25 MB on free tier). Issue presigned part URLs and have the client upload directly to R2.
- **Part size below 5 MB (except the last part)** — R2 enforces a 5 MB minimum for non-terminal parts. Parts smaller than this result in `EntityTooSmall` errors from the S3-compatible endpoint.
- **Neglecting to abort incomplete multipart uploads** — incomplete uploads in R2 accumulate storage costs. Always implement an abort endpoint and call it on user cancellation. Consider a Workers Cron that runs `listMultipartUploads` and aborts any session older than 24 hours.
- **Reading the entire file into memory before chunking** — `FileSystem.readAsStringAsync` with Base64 encoding loads the full chunk into JS heap. For very large files (>100 MB), prefer `expo-file-system`'s `createUploadTask` for individual parts to avoid OOM crashes on low-memory devices.

---

## Gotchas

- **ETag format**: R2 returns ETags without quotes in some SDK versions and with quotes in others. Strip surrounding quotes with `.replace(/"/g, '')` before sending ETags to the `CompleteMultipartUpload` call.
- **iOS background upload**: if the user backgrounds the app mid-upload, iOS may suspend the JS runtime. For files > 20 MB, use `expo-background-fetch` or a native background URLSession via a custom Expo module.
- **Android `FileSystem.readAsStringAsync` offset**: the `position` + `length` options require `expo-file-system` >= 15.0. Older versions require reading the whole file and slicing the Base64 string manually.
- **CORS on R2 presigned URLs**: presigned `PUT` URLs bypass CORS only for the exact HTTP method they were signed for. If the browser/WebView also needs to access the R2 object, configure CORS on the R2 bucket separately from the presigned URL.
- **Clock drift**: presigned URLs embed a timestamp. If the device clock is off by more than 15 minutes, R2 rejects the request with `RequestTimeTooSkewed`. Sync device time before generating URLs (the Worker timestamp is always authoritative — see `cloudflare-r2-presigned-url-mobile-clock-drift.md`).
- **Part numbering is 1-based**: part numbers must be integers from 1 to 10,000. Off-by-one errors (0-based arrays) cause `InvalidPart` errors.

---

## Verification

```bash
# Check for any incomplete multipart uploads (potential storage leaks)
wrangler r2 object list example project-assets --prefix uploads/

# From within a Worker test or curl, verify initiate returns valid URLs
curl -X POST https://api.example.com/upload/initiate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"filename":"test.jpg","contentType":"image/jpeg","sizeBytes":10485760}' | jq .

# Verify a presigned URL is usable (returns 200/403)
curl -o /dev/null -s -w "%{http_code}" \
  -X PUT "<presigned-part-url>" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/tmp/test-chunk-5mb.bin
```

---

## Related

- `react-native-cloudflare-worker-upload.md` — Single-PUT upload via Worker (for files < 5 MB)
- `cloudflare-r2-presigned-url-mobile-clock-drift.md` — Presigned URL clock drift issues on mobile
- `react-native-image-picker.md` — Image and file picking patterns
- `mobile-network-resilience.md` — Retry and backoff strategies for mobile uploads
- `image-upload-compression-client-side.md` — Client-side image compression before upload

---

## Sources

- [R2 S3-compatible multipart upload API](https://developers.cloudflare.com/r2/api/s3/multipart-uploads/)
- [AWS SDK v3 `@aws-sdk/s3-request-presigner`](https://docs.aws.amazon.com/AWSJavaScriptSDK/v3/latest/modules/_aws_sdk_s3_request_presigner.html)
- [expo-file-system `readAsStringAsync` position/length](https://docs.expo.dev/versions/latest/sdk/filesystem/#filesystemreadasstringasyncfileuri-options)
- [React Native XMLHttpRequest upload progress](https://reactnative.dev/docs/network#using-fetch)
- [R2 object size limits and multipart rules](https://developers.cloudflare.com/r2/objects/multipart-objects/)
