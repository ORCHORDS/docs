# R2 Multipart Upload Abuse Prevention and Size Limits in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

An attacker initiates thousands of R2 multipart uploads, uploads large parts, and never completes or aborts them. The orphaned parts accumulate indefinitely, generating storage costs for the account owner without producing any usable objects. Alternatively, a user bypasses the advertised per-file size limit by uploading many oversized parts in parallel, exhausting R2 storage quotas or downstream processing pipelines.

## Context

Cloudflare R2 supports the S3-compatible multipart upload API: `createMultipartUpload`, `uploadPart`, `completeMultipartUpload`, and `abortMultipartUpload`. Incomplete multipart uploads do not appear as R2 objects and are not subject to lifecycle rules by default, making them invisible to ordinary bucket audits. Because Workers expose the full multipart API via `env.R2.createMultipartUpload()`, every Workers endpoint that proxies uploads must enforce size limits, part count caps, upload-session TTLs, and authenticated ownership before allowing parts to land.

## 1. Enforcing Part Size and Count Limits in the Worker

```typescript
const MAX_PART_SIZE_BYTES = 100 * 1024 * 1024; // 100 MiB per part
const MAX_PART_COUNT = 50;                       // 50 parts → max 5 GiB per object
const UPLOAD_SESSION_TTL_MS = 30 * 60 * 1000;   // 30-minute session window

interface Env {
  R2: R2Bucket;
  KV: KVNamespace; // tracks active upload sessions
}

export async function handleUploadPart(
  request: Request,
  env: Env,
  uploadId: string,
  partNumber: number
): Promise<Response> {
  // 1. Validate session ownership and TTL
  const session = await env.KV.get<UploadSession>(`mpu:${uploadId}`, "json");
  if (!session) return new Response("Unknown upload session", { status: 404 });

  const userId = getUserId(request); // from validated JWT
  if (session.ownerId !== userId)
    return new Response("Forbidden", { status: 403 });

  if (Date.now() > session.expiresAt)
    return new Response("Upload session expired", { status: 410 });

  // 2. Enforce part count
  if (partNumber > MAX_PART_COUNT)
    return new Response(`Part number exceeds maximum of ${MAX_PART_COUNT}`, { status: 400 });

  // 3. Enforce part size via Content-Length
  const contentLength = parseInt(request.headers.get("content-length") ?? "0");
  if (contentLength > MAX_PART_SIZE_BYTES)
    return new Response("Part too large", { status: 413 });

  const part = await session.mpuObject.uploadPart(partNumber, request.body!);
  return Response.json({ etag: part.etag, partNumber });
}
```

## 2. Tracking Upload Sessions in KV with Expiry

```typescript
interface UploadSession {
  uploadId: string;
  key: string;
  ownerId: string;
  expiresAt: number;
  partsUploaded: number;
}

export async function handleCreateMultipartUpload(
  request: Request,
  env: Env,
  key: string
): Promise<Response> {
  const userId = getUserId(request);
  const mpu = await env.R2.createMultipartUpload(key, {
    httpMetadata: { contentType: request.headers.get("content-type") ?? "application/octet-stream" },
  });

  const session: UploadSession = {
    uploadId: mpu.uploadId,
    key,
    ownerId: userId,
    expiresAt: Date.now() + UPLOAD_SESSION_TTL_MS,
    partsUploaded: 0,
  };

  // TTL-based KV entry: auto-expires after 30 minutes
  await env.KV.put(`mpu:${mpu.uploadId}`, JSON.stringify(session), {
    expirationTtl: 1800,
  });

  return Response.json({ uploadId: mpu.uploadId });
}
```

## 3. Aborting Expired Sessions via a Cron Worker

Orphaned multipart uploads that expired without completion must be actively aborted so parts are freed:

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // List all tracked sessions in KV
    const list = await env.KV.list({ prefix: "mpu:" });

    for (const { name } of list.keys) {
      const session = await env.KV.get<UploadSession>(name, "json");
      if (!session) continue;

      if (Date.now() > session.expiresAt) {
        try {
          const mpu = env.R2.resumeMultipartUpload(session.key, session.uploadId);
          await mpu.abort();
          console.log(`Aborted expired MPU: ${session.uploadId}`);
        } catch (err) {
          // Already completed or aborted; safe to ignore
          console.warn(`Could not abort ${session.uploadId}:`, err);
        }
        await env.KV.delete(name);
      }
    }
  },
};
```

Configure in `wrangler.toml`:

```toml
[[triggers.crons]]
cron = "*/15 * * * *"   # run every 15 minutes
```

## 4. Enforcing Total Object Size on Completion

```typescript
export async function handleCompleteMultipartUpload(
  request: Request,
  env: Env,
  uploadId: string
): Promise<Response> {
  const session = await env.KV.get<UploadSession>(`mpu:${uploadId}`, "json");
  if (!session || session.ownerId !== getUserId(request))
    return new Response("Forbidden", { status: 403 });

  const { parts }: { parts: R2UploadedPart[] } = await request.json();

  // Enforce total object size: parts.length * max_part_size as a heuristic upper bound
  if (parts.length > MAX_PART_COUNT)
    return new Response("Too many parts", { status: 400 });

  const mpu = env.R2.resumeMultipartUpload(session.key, session.uploadId);
  const object = await mpu.complete(parts);
  await env.KV.delete(`mpu:${uploadId}`);

  return Response.json({ key: object.key, etag: object.httpEtag });
}
```

## 5. WAF Rate Limiting on Multipart Upload Endpoints

Add a Cloudflare Rate Limiting rule targeting the multipart upload initiation path to cap the number of sessions any single IP or authenticated user can open:

```
Expression: (http.request.uri.path contains "/upload/initiate") and
            (cf.threat_score < 10)
Rate:        5 requests per minute per IP
Action:      Block (429)
```

Additionally, for authenticated routes, enforce per-user limits using a Durable Object counter keyed on `userId` to prevent credential-sharing abuse that bypasses IP-based limits.

## 6. Monitoring Orphaned Parts via Analytics Engine

```typescript
export async function emitMpuMetrics(
  env: Env & { AE: AnalyticsEngineDataset },
  event: "created" | "completed" | "aborted" | "expired",
  uploadId: string,
  sizeBytes?: number
): Promise<void> {
  env.AE.writeDataPoint({
    blobs: [event, uploadId],
    doubles: [sizeBytes ?? 0],
    indexes: [event],
  });
}
```

Query the dataset in Workers Analytics Engine SQL API to alert when the ratio of expired-to-completed uploads exceeds 10%, indicating active abuse.

## Anti-patterns

- Allowing unauthenticated multipart upload initiation — any visitor can generate orphaned parts.
- Not setting a KV TTL on the upload session — abandoned sessions are never cleaned up.
- Trusting the `Content-Length` header alone without reading the body stream length — an attacker can lie about content length when the Worker streams directly to R2.
- Completing a multipart upload without verifying the ETags supplied match the parts actually uploaded by the authenticated user.
- Allowing unlimited `partNumber` values — R2 supports up to 10,000 parts; accepting all of them without a per-user cap enables 500 GiB per upload.

## Gotchas

- R2's `createMultipartUpload` returns an `R2MultipartUpload` object that holds an internal reference; you cannot serialize it to KV directly. Store only `uploadId` and `key`, then call `env.R2.resumeMultipartUpload(key, uploadId)` in subsequent requests.
- KV TTL is in seconds (`expirationTtl: 1800`) but `Date.now()` is in milliseconds — be consistent.
- The cron-based abort loop must handle the case where the R2 multipart upload has already been completed or aborted by the client; calling `abort()` on a completed upload throws.
- Cloudflare R2 does not currently support automatic lifecycle policies for incomplete multipart uploads (unlike AWS S3 lifecycle rules); the cleanup cron is mandatory.

## Verification

```bash
# Confirm no orphaned MPU sessions older than 30 min remain
wrangler kv key list --binding KV --prefix "mpu:" \
  | jq '[.[] | select(.expiration < now)] | length'

# Simulate abuse: open 10 MPU sessions without completing
for i in $(seq 1 10); do
  curl -X POST https://api.example.com/upload/initiate \
    -H "Authorization: Bearer $TOKEN" -d '{"filename":"test.bin"}'
done

# Verify the 6th request is rate-limited (429)
curl -o /dev/null -w "%{http_code}" \
  -X POST https://api.example.com/upload/initiate \
  -H "Authorization: Bearer $TOKEN" -d '{"filename":"abuse.bin"}'
```

## Related

- `r2-presigned-url-security.md`
- `r2-object-key-enumeration-prevention.md`
- `r2-bucket-public-exposure-audit.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `file-upload-security-pipeline.md`

## Sources

- Cloudflare R2 Multipart Upload API: https://developers.cloudflare.com/r2/api/workers/workers-api-usage/#multipart-upload
- S3 Multipart Upload Guide (patterns apply to R2): https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html
- OWASP Unrestricted File Upload: https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload
