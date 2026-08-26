# R2 Presigned URL Expiry Misconfiguration Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

After a refactor of the file-upload service, 8% of upload attempts began failing with HTTP 403 `SignatureDoesNotMatch` errors within seconds of the user receiving the presigned URL. Users on slower connections and mobile networks were disproportionately affected. The error rate climbed during peak hours and was zero during off-peak periods.

## Context

The upload flow mints an R2 presigned URL in a Worker, returns it to the browser, and the browser PUTs the file directly to R2. The refactor moved URL generation from a synchronous path (Worker generates URL immediately on POST /upload/init) to an async path (Worker enqueues a job, Queues consumer generates the URL, sends it back via a WebSocket). The consumer ran in a separate Worker with a clock that was not validated. The presigned URL expiry had always been set to 300 seconds, but the consumer's processing delay meant the URL was already 60–180 seconds old before the client received it.

---

## Root Cause: Expiry Clock Starts at Signing Time, Not Delivery Time

R2 presigned URLs use HMAC-SHA256 signatures tied to an expiry expressed as seconds from the signing instant (`X-Amz-Expires`). The expiry countdown begins the moment the URL is signed, not when the client receives it.

```typescript
// BEFORE — expiry did not account for delivery latency
async function generateUploadUrl(
  env: Env,
  key: string,
): Promise<string> {
  // Expiry starts NOW, not when the client receives this
  const url = await env.BUCKET.createMultipartUpload(key);

  return await env.BUCKET.createPresignedUrl("PUT", key, {
    expiresIn: 300, // 5 minutes — but ~2 min already gone by delivery
  });
}
```

On a slow mobile connection the user received the URL 180 s after signing. With only 120 s remaining and a multi-megabyte upload to complete, many uploads expired mid-flight.

## Fix Step 1: Budget Expiry to Include Delivery and Upload Time

Calculate expiry from the expected delivery latency and the maximum upload duration for the file size limit.

```typescript
// src/upload/presign.ts

const DELIVERY_BUDGET_S = 30;      // time for URL to reach client
const BYTES_PER_SECOND = 50_000;   // conservative mobile throughput (~400 kbps)
const MINIMUM_EXPIRY_S = 60;       // floor — never shorter than this

export function computeExpirySeconds(fileSizeBytes: number): number {
  const uploadSeconds = Math.ceil(fileSizeBytes / BYTES_PER_SECOND);
  return Math.max(
    DELIVERY_BUDGET_S + uploadSeconds,
    MINIMUM_EXPIRY_S,
  );
}

export async function generateUploadUrl(
  bucket: R2Bucket,
  key: string,
  fileSizeBytes: number,
): Promise<{ url: string; expiresInSeconds: number }> {
  const expiresIn = computeExpirySeconds(fileSizeBytes);

  const url = await (bucket as unknown as {
    createPresignedUrl(
      method: string,
      key: string,
      opts: { expiresIn: number },
    ): Promise<string>;
  }).createPresignedUrl("PUT", key, { expiresIn });

  return { url, expiresIn };
}
```

## Fix Step 2: Return Expiry Metadata to the Client

The client should know when the URL expires so it can request a fresh one if needed.

```typescript
// src/routes/upload.ts
export async function handleUploadInit(
  request: Request,
  env: Env,
): Promise<Response> {
  const { fileName, fileSizeBytes } = await request.json<{
    fileName: string;
    fileSizeBytes: number;
  }>();

  const key = `uploads/${crypto.randomUUID()}/${fileName}`;
  const { url, expiresIn } = await generateUploadUrl(
    env.BUCKET,
    key,
    fileSizeBytes,
  );

  const expiresAt = Date.now() + expiresIn * 1000;

  return Response.json({
    uploadUrl: url,
    key,
    expiresAt,            // ISO timestamp; client renders countdown or retries
    expiresInSeconds: expiresIn,
  });
}
```

## Fix Step 3: Client-Side Pre-flight Expiry Check

```typescript
// client/upload.ts
interface UploadTicket {
  uploadUrl: string;
  key: string;
  expiresAt: number; // Unix ms
}

async function uploadFile(ticket: UploadTicket, file: File): Promise<void> {
  const remainingMs = ticket.expiresAt - Date.now();
  const estimatedUploadMs = (file.size / 50_000) * 1000; // 400 kbps

  if (remainingMs < estimatedUploadMs + 5_000) {
    // Less than upload time + 5 s buffer remaining — refresh the ticket
    const fresh = await refreshUploadTicket(ticket.key, file.size);
    return uploadFile(fresh, file);
  }

  const response = await fetch(ticket.uploadUrl, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": file.type },
  });

  if (response.status === 403) {
    throw new Error(`Upload rejected (403): URL may have expired`);
  }
  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }
}
```

## Fix Step 4: Instrument Presigned URL Age at Time of Use

Log the signed-at timestamp inside the URL's query parameters for debugging:

```typescript
// src/upload/presign.ts (updated)
export async function generateUploadUrl(
  bucket: R2Bucket,
  key: string,
  fileSizeBytes: number,
): Promise<{ url: string; expiresAt: number; signedAt: number }> {
  const signedAt = Date.now();
  const expiresIn = computeExpirySeconds(fileSizeBytes);

  const rawUrl = await (bucket as BucketWithPresign).createPresignedUrl(
    "PUT",
    key,
    { expiresIn },
  );

  // Append non-functional tag for observability (does not affect signature)
  const url = new URL(rawUrl);
  url.searchParams.set("x-signed-at", signedAt.toString());

  return {
    url: url.toString(),
    expiresAt: signedAt + expiresIn * 1000,
    signedAt,
  };
}
```

## Fix Step 5: Add Expiry Regression Test

```typescript
// tests/upload/presign.test.ts
import { describe, it, expect } from "vitest";
import { computeExpirySeconds } from "../../src/upload/presign";

describe("computeExpirySeconds", () => {
  it("provides enough time for a 10 MB file on slow mobile", () => {
    const tenMb = 10 * 1024 * 1024;
    const expiry = computeExpirySeconds(tenMb);
    const uploadTime = tenMb / 50_000;
    // Must cover delivery + upload with margin
    expect(expiry).toBeGreaterThan(uploadTime + 30);
  });

  it("never returns less than the minimum", () => {
    expect(computeExpirySeconds(1)).toBeGreaterThanOrEqual(60);
  });

  it("caps at a sensible maximum for very large files", () => {
    const oneGb = 1024 ** 3;
    expect(computeExpirySeconds(oneGb)).toBeLessThanOrEqual(86_400);
  });
});
```

---

## Anti-Patterns

- **Setting a flat expiry without modelling delivery latency.** `expiresIn: 300` is meaningless if the URL takes 3 minutes to reach the client.
- **Not returning `expiresAt` to the client.** Without this the client cannot detect imminent expiry or decide whether to refresh before uploading.
- **Generating presigned URLs inside async/queued flows without adjusting expiry.** The gap between signing and delivery can be minutes in queue-backed architectures.
- **Relying on the 403 response to surface expiry.** R2 returns the same `SignatureDoesNotMatch` for a bad key, wrong method, and expired URL; distinguishing them requires knowing when the URL was signed.

## Gotchas

- R2 presigned URL maximum expiry is 7 days (`604800` seconds). Requesting more throws an error.
- Clock skew between the Workers runtime and R2's signing service can cause a URL that appears valid to be rejected. The Workers clock is NTP-synced but can drift ±1–2 s; add a 10 s buffer to the minimum expiry.
- Multipart upload presigned URLs (for large files) are separate from single-PUT URLs. Multipart part URLs each carry their own expiry and must be refreshed independently if an upload stalls.
- The `x-signed-at` tag appended to the URL does not survive URL re-encoding by some HTTP clients. Keep it short and ASCII-safe.

## Verification

1. Upload success rate returns to > 99.5% across all file sizes.
2. Zero HTTP 403 errors during normal upload flows in staging with throttled network (Chrome DevTools: 100 kbps preset).
3. `computeExpirySeconds` unit tests pass for 1 B, 10 MB, 100 MB, and 1 GB inputs.
4. Observability: `x-signed-at` appears in R2 access logs; p99 URL age at first PUT byte is < 30 s.
5. Client pre-flight check triggers a refresh at least once during a simulated slow-delivery test.

## Related

- `r2-presigned-url-race-condition-upload-incident.md`
- `r2-multipart-upload-size-limit-lesson.md`
- `workers-clock-skew-jwt-expiry-incident.md`
- `timeouts-everywhere-no-exceptions.md`

## Sources

- Cloudflare R2 Presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- AWS S3 Presigned URL Expiry: https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html
- R2 S3-Compatible API Limits: https://developers.cloudflare.com/r2/reference/s3-compatibility/
