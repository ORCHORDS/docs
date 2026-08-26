# R2 Presigned URL Direct Client Upload Pattern

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Users must upload large files (avatars, attachments, exports) to your example project application. Routing
the binary through a Worker adds latency, consumes CPU ms, and runs into the 100 MB request body
limit on the Free plan. You want the client to upload directly to R2 without exposing bucket
credentials.

## Context

Cloudflare R2 supports **presigned URLs** compatible with the AWS S3 API. A Worker generates a
time-limited signed URL (using the `aws4fetch` library and R2 S3-compatible API credentials), hands
it to the client, and the client PUTs the file directly to that URL — bypassing the Worker entirely
for the binary payload. The Worker only records metadata in D1 after the client confirms success.

R2 presigned URLs expire in 15 minutes by default (configurable up to 7 days). The signature covers
the bucket name, key, HTTP method, and optional content-type, preventing the client from uploading
to arbitrary paths.

---

## Prerequisites: R2 S3-Compatible Credentials

```bash
# Create an API token with R2 write permissions
# In Cloudflare Dashboard → R2 → Manage API tokens → Create Token
# Note: Access Key ID and Secret Access Key
```

Store them as Workers secrets:

```bash
npx wrangler secret put R2_ACCESS_KEY_ID
npx wrangler secret put R2_SECRET_ACCESS_KEY
```

```toml
# wrangler.toml
[[r2_buckets]]
binding     = "ASSETS_BUCKET"
bucket_name = "example project-assets"

[vars]
R2_ACCOUNT_ID   = "<cloudflare-account-id>"
R2_BUCKET_NAME  = "example project-assets"
```

---

## Environment Types

```typescript
// src/types.ts
export interface Env {
  ASSETS_BUCKET:      R2Bucket;
  R2_ACCESS_KEY_ID:   string;
  R2_SECRET_ACCESS_KEY: string;
  R2_ACCOUNT_ID:      string;
  R2_BUCKET_NAME:     string;
  DB:                 D1Database;
}
```

---

## Presigned URL Generator (Worker)

```typescript
// src/r2/presign.ts
import { AwsClient } from "aws4fetch";

export interface PresignOptions {
  key:         string;   // R2 object key, e.g. "uploads/user-42/avatar.jpg"
  contentType: string;
  expiresIn:   number;   // seconds, max 604800 (7 days)
}

export async function generatePresignedPutUrl(
  env: Env,
  opts: PresignOptions
): Promise<string> {
  const client = new AwsClient({
    accessKeyId:     env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    region:          "auto",
    service:         "s3",
  });

  const endpoint =
    `https://${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com` +
    `/${env.R2_BUCKET_NAME}/${opts.key}`;

  const url = new URL(endpoint);
  url.searchParams.set("X-Amz-Expires", String(opts.expiresIn));

  const signed = await client.sign(
    new Request(url.toString(), { method: "PUT" }),
    {
      aws: { signQuery: true },  // embed signature in query string, not header
    }
  );

  return signed.url;
}
```

---

## Worker Handler: Issue Presigned URL

```typescript
// src/handlers/upload.ts
import { generatePresignedPutUrl } from "../r2/presign";

export async function handleRequestUploadUrl(
  request: Request,
  env: Env
): Promise<Response> {
  const { filename, contentType, userId } =
    await request.json<{ filename: string; contentType: string; userId: string }>();

  // Sanitise key — never allow client to choose arbitrary R2 paths
  const ext = filename.split(".").pop()?.toLowerCase() ?? "bin";
  const key = `uploads/${userId}/${crypto.randomUUID()}.${ext}`;

  const presignedUrl = await generatePresignedPutUrl(env, {
    key,
    contentType,
    expiresIn: 900, // 15 minutes
  });

  // Store pending upload metadata in D1 so we can verify completion later
  await env.DB.prepare(
    `INSERT INTO pending_uploads (key, user_id, content_type, expires_at)
     VALUES (?1, ?2, ?3, datetime('now', '+15 minutes'))`
  ).bind(key, userId, contentType).run();

  return Response.json({ uploadUrl: presignedUrl, key });
}
```

---

## Worker Handler: Confirm Upload

After the client finishes the PUT, it calls this endpoint so the Worker can validate the object
actually exists in R2 and commit the metadata to D1:

```typescript
// src/handlers/upload.ts (continued)
export async function handleConfirmUpload(
  request: Request,
  env: Env
): Promise<Response> {
  const { key, userId } = await request.json<{ key: string; userId: string }>();

  // Verify the object exists and belongs to this user
  const pending = await env.DB.prepare(
    `SELECT key FROM pending_uploads
     WHERE key = ?1 AND user_id = ?2 AND expires_at > datetime('now')`
  ).bind(key, userId).first<{ key: string }>();

  if (!pending) return Response.json({ error: "Unknown or expired upload" }, { status: 404 });

  const obj = await env.ASSETS_BUCKET.head(key);
  if (!obj) return Response.json({ error: "Object not found in R2" }, { status: 404 });

  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO assets (key, user_id, size, content_type, created_at)
       VALUES (?1, ?2, ?3, ?4, datetime('now'))`
    ).bind(key, userId, obj.size, obj.httpMetadata?.contentType ?? "application/octet-stream"),
    env.DB.prepare("DELETE FROM pending_uploads WHERE key = ?1").bind(key),
  ]);

  return Response.json({ success: true, key, size: obj.size });
}
```

---

## Client-Side Upload Flow

```typescript
// browser / React client
async function uploadFile(file: File, userId: string) {
  // Step 1: get a presigned URL from the Worker
  const { uploadUrl, key } = await fetch("/api/upload/request", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ filename: file.name, contentType: file.type, userId }),
  }).then((r) => r.json());

  // Step 2: PUT directly to R2 — no Worker proxy
  await fetch(uploadUrl, {
    method:  "PUT",
    headers: { "Content-Type": file.type },
    body:    file,
  });

  // Step 3: confirm with Worker so D1 metadata is written
  await fetch("/api/upload/confirm", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ key, userId }),
  });
}
```

---

## Anti-patterns

- **Proxying the binary through the Worker**: exceeds the 100 MB body limit and wastes CPU ms;
  always presign and let the client PUT directly.
- **Letting the client choose the R2 key freely**: an attacker could overwrite another user's
  objects. Always generate the key server-side from a `randomUUID()` + userId prefix.
- **Skipping the confirm step**: without verifying the object exists in R2, D1 may record metadata
  for an upload that never completed.
- **Long expiry on sensitive buckets**: a 7-day presigned URL for a private document is a large
  attack window; use 15 minutes for user uploads.

---

## Gotchas

- `aws4fetch` must be listed in `package.json` — it is not bundled into the Workers runtime.
  Install via `npm install aws4fetch`.
- R2 S3-compatible endpoint uses the account ID, not a region name:
  `<account-id>.r2.cloudflarestorage.com`. The `region` field in `AwsClient` must be `"auto"`.
- Cross-origin PUT from a browser requires CORS configured on the R2 bucket. Add a CORS policy in
  the Cloudflare Dashboard → R2 → Bucket settings → CORS, allowing the `PUT` method from your
  origin.
- Presigned URLs for GET (downloads) follow the same pattern but use `method: "GET"` and
  `aws: { signQuery: true }`.

---

## Verification

```bash
# 1. Request a presigned URL
RESPONSE=$(curl -s -X POST https://example project.example.com/api/upload/request \
  -H "Content-Type: application/json" \
  -d '{"filename":"test.txt","contentType":"text/plain","userId":"u-1"}')
URL=$(echo $RESPONSE | jq -r '.uploadUrl')
KEY=$(echo $RESPONSE | jq -r '.key')

# 2. PUT directly to R2
curl -X PUT "$URL" -H "Content-Type: text/plain" --data "hello world"

# 3. Confirm
curl -X POST https://example project.example.com/api/upload/confirm \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"$KEY\",\"userId\":\"u-1\"}"
```

---

## Related

- `d1-r2-blob-offload-metadata-pattern-workers.md`
- `d1-text-compression-r2-offload.md`
- `d1-audit-event-log.md`
- `database-encryption-at-rest.md`

## Sources

- Cloudflare R2 S3-compatible API: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- aws4fetch library: https://github.com/mhart/aws4fetch
- R2 CORS configuration: https://developers.cloudflare.com/r2/buckets/cors/
