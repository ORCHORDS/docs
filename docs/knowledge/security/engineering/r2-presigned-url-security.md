# R2 Pre-signed URL Security: Expiry, Scope, and Access Control

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

An application stores user files in Cloudflare R2. Direct public bucket access exposes every object to anyone with the URL. Backend-proxied downloads create a bottleneck and add egress cost. The middle ground is pre-signed URLs: short-lived, scoped tokens that grant temporary read (or write) access to a specific R2 object without exposing the bucket's credentials or making the bucket globally public.

Common failure modes in pre-signed URL implementations:

- URLs with excessively long expiry (hours or days) that can be screenshot-shared or intercepted
- Missing user-to-object authorization (any authenticated user gets any object)
- No binding of the URL to a specific HTTP method (a GET presign being reused for a PUT)
- No revocation mechanism when a user's access is removed mid-session

## Context

Cloudflare R2 implements an S3-compatible pre-signing API. The `aws4fetch` library (or the `@aws-sdk/s3-request-presigner` with an R2-compatible endpoint) generates signed URLs using the R2 access key pair. The resulting URL is self-contained: the signature encodes the object key, HTTP method, expiry time, and bucket. The R2 storage layer validates the signature and timestamp on every request.

Key security properties:

- **Method-scoped**: a presign for `GET` cannot be used for `PUT` (and vice versa)
- **Key-scoped**: the signature covers the exact object path; a URL for `user-123/report.pdf` cannot access `user-456/report.pdf`
- **Time-limited**: requests after the `X-Amz-Expires` window return 403
- **Credential-independent**: the R2 access key never leaves the Worker; the presigned URL contains only its derived signature

## Generating Pre-signed URLs in a Worker

Use `aws4fetch` to create pre-signed URLs without pulling in the full AWS SDK:

```typescript
// src/lib/r2-presign.ts
import { AwsClient } from 'aws4fetch';

export interface R2PresignOptions {
  bucket: string;
  key: string;
  method: 'GET' | 'PUT';
  expiresInSeconds: number;
  accountId: string;
  accessKeyId: string;
  secretAccessKey: string;
}

export async function presignR2Url(opts: R2PresignOptions): Promise<string> {
  const {
    bucket, key, method, expiresInSeconds,
    accountId, accessKeyId, secretAccessKey,
  } = opts;

  if (expiresInSeconds > 3600) {
    throw new Error('Pre-signed URL expiry must not exceed 3600 seconds (1 hour)');
  }

  const client = new AwsClient({
    accessKeyId,
    secretAccessKey,
    service: 's3',
    region: 'auto',
  });

  const endpoint = `https://${accountId}.r2.cloudflarestorage.com`;
  const objectUrl = `${endpoint}/${bucket}/${encodeURIComponent(key)}`;

  const signed = await client.sign(
    new Request(objectUrl, { method }),
    {
      aws: {
        signQuery: true,           // puts credentials in query string, not headers
        expiresIn: expiresInSeconds,
        allHeaders: false,
      },
    },
  );

  return signed.url;
}
```

Always gate presign generation behind an authorization check:

```typescript
// src/handlers/download.ts
import { presignR2Url } from '../lib/r2-presign';
import { getUserFromSession } from '../lib/auth';

interface Env {
  R2_ACCOUNT_ID: string;
  R2_ACCESS_KEY_ID: string;
  R2_SECRET_ACCESS_KEY: string;
  R2_BUCKET_NAME: string;
  DB: D1Database;
  SESSIONS: KVNamespace;
}

export async function handleDownload(req: Request, env: Env): Promise<Response> {
  // 1. Authenticate the caller
  const sessionToken = req.headers.get('Authorization')?.replace('Bearer ', '');
  if (!sessionToken) {
    return new Response(JSON.stringify({ error: 'Unauthenticated' }), { status: 401 });
  }

  const user = await getUserFromSession(sessionToken, env.SESSIONS);
  if (!user) {
    return new Response(JSON.stringify({ error: 'Invalid session' }), { status: 401 });
  }

  // 2. Extract the requested object key from the URL path
  const url = new URL(req.url);
  const rawKey = url.pathname.replace(/^\/api\/download\//, '');
  if (!rawKey) {
    return new Response(JSON.stringify({ error: 'Missing object key' }), { status: 400 });
  }

  // 3. Authorise: verify this user owns (or has access to) the object
  //    Object keys are namespaced per user: "uploads/{userId}/{filename}"
  const expectedPrefix = `uploads/${user.id}/`;
  const objectKey = decodeURIComponent(rawKey);

  if (!objectKey.startsWith(expectedPrefix)) {
    // Log this — it may indicate IDOR probing
    console.warn('Unauthorised R2 key access attempt', {
      userId: user.id,
      requestedKey: objectKey,
    });
    return new Response(JSON.stringify({ error: 'Forbidden' }), { status: 403 });
  }

  // 4. Generate the pre-signed URL with a tight expiry
  let signedUrl: string;
  try {
    signedUrl = await presignR2Url({
      bucket: env.R2_BUCKET_NAME,
      key: objectKey,
      method: 'GET',
      expiresInSeconds: 300,  // 5 minutes — short enough for most use cases
      accountId: env.R2_ACCOUNT_ID,
      accessKeyId: env.R2_ACCESS_KEY_ID,
      secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    });
  } catch (err) {
    console.error('Pre-sign failed', err);
    return new Response(JSON.stringify({ error: 'Failed to generate download link' }), {
      status: 500,
    });
  }

  // 5. Return the URL — do NOT redirect to it server-side;
  //    let the client initiate the request so its IP is the one verified
  return new Response(JSON.stringify({ url: signedUrl, expiresInSeconds: 300 }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',   // Do not cache URLs containing credentials
    },
  });
}
```

## Secure Upload Flow (Client-Driven PUT Pre-sign)

For direct browser-to-R2 uploads, use a PUT pre-signed URL. The Worker verifies file metadata before issuing the URL and the client uploads directly:

```typescript
// src/handlers/upload-presign.ts
import { presignR2Url } from '../lib/r2-presign';
import { getUserFromSession } from '../lib/auth';
import { generateId } from '../lib/id';

const ALLOWED_CONTENT_TYPES = new Set([
  'image/jpeg', 'image/png', 'image/webp', 'application/pdf',
]);
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10 MB

export async function handleUploadPresign(req: Request, env: Env): Promise<Response> {
  const user = await getUserFromSession(
    req.headers.get('Authorization')?.replace('Bearer ', '') ?? '',
    env.SESSIONS,
  );
  if (!user) {
    return new Response(JSON.stringify({ error: 'Unauthenticated' }), { status: 401 });
  }

  const { filename, contentType, contentLength } = await req.json<{
    filename: string;
    contentType: string;
    contentLength: number;
  }>();

  // Validate declared MIME type against allowlist
  if (!ALLOWED_CONTENT_TYPES.has(contentType)) {
    return new Response(JSON.stringify({ error: 'Content type not permitted' }), {
      status: 415,
    });
  }

  if (contentLength > MAX_UPLOAD_BYTES) {
    return new Response(JSON.stringify({ error: 'File too large' }), { status: 413 });
  }

  // Sanitise the filename — never trust client-supplied names as object keys directly
  const safeFilename = filename.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 128);
  const objectKey = `uploads/${user.id}/${generateId()}-${safeFilename}`;

  const uploadUrl = await presignR2Url({
    bucket: env.R2_BUCKET_NAME,
    key: objectKey,
    method: 'PUT',
    expiresInSeconds: 600,  // 10 minutes — enough for large uploads on slow connections
    accountId: env.R2_ACCOUNT_ID,
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  });

  // Record the pending upload so we can validate it after completion
  await env.DB.prepare(
    'INSERT INTO pending_uploads (object_key, user_id, content_type, expires_at) VALUES (?, ?, ?, ?)',
  ).bind(objectKey, user.id, contentType, Date.now() + 600_000).run();

  return new Response(JSON.stringify({ uploadUrl, objectKey }), {
    status: 200,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  });
}
```

## Wrangler Secrets for R2 Credentials

```toml
# wrangler.toml — public configuration only
[vars]
R2_ACCOUNT_ID = "abc123..."
R2_BUCKET_NAME = "user-uploads-prod"

# R2 access key ID can be stored as a var (it identifies but does not authenticate),
# but the secret access key must always be a secret.
```

```bash
# Store credentials securely
wrangler secret put R2_ACCESS_KEY_ID --env production
wrangler secret put R2_SECRET_ACCESS_KEY --env production

# Verify (values remain hidden)
wrangler secret list --env production
```

Create a dedicated R2 API token with minimal permissions:

1. Cloudflare Dashboard → R2 → Manage R2 API Tokens
2. Create a token with **Object Read & Write** permission scoped to the specific bucket
3. Do not use the account-level API token for R2 presigning

## Anti-patterns

- **Expiry of 24 hours or more**: A presigned URL is a credential. Long-lived URLs persist in browser history, CDN logs, and referrer headers. Cap GET URLs at 5–15 minutes and PUT URLs at 10–30 minutes.
- **Returning a redirect (302) to the presigned URL**: The presigned URL will appear in server access logs, CDN access logs, and the `Referer` header of sub-resources loaded by the destination page. Return the URL as JSON and let the client initiate its own request.
- **Skipping the authorization check before presigning**: The Worker must confirm the requesting user owns the object before generating a URL. Never presign based solely on the object key from the request without a database lookup.
- **Using the account-level API key for presigning**: This key has access to all R2 buckets and all account resources. A leak compromises everything. Use a scoped R2 API token.
- **Caching presigned URLs in a shared cache**: Do not store presigned URLs in a CDN cache or KV cache shared across users. If cached and served to the wrong user, it bypasses the auth check.
- **Trusting `Content-Type` in PUT uploads without server-side re-validation**: The declared `contentType` in the presign request is not enforced by R2. Run a server-side MIME sniff after upload completion (read the first 512 bytes) before marking the object as available.

## Gotchas

- **Clock skew**: R2 validates the timestamp in the presigned URL against its own clock. If the Worker's clock (or the client's clock for client-generated URLs) drifts more than ±15 minutes, the signature is rejected. Workers clocks are NTP-synced; this is only an issue if you generate presigned URLs outside of Workers (e.g., in a mobile app).
- **URL encoding of object keys**: Spaces, Unicode, and special characters in filenames must be percent-encoded in the object key before signing. `encodeURIComponent` handles this; raw string concatenation does not.
- **No URL revocation in R2**: Once issued, a presigned URL is valid until it expires. There is no server-side blocklist. Design expiry windows to match the worst-case credential exposure you can accept. For sensitive documents, use 60-second expiry and re-issue on page load.
- **CORS on R2 bucket for direct uploads**: For browser-initiated PUT requests, the R2 bucket needs a CORS rule permitting `PUT` from your app's origin. Configure this under R2 bucket settings, not in the Worker.
- **`aws4fetch` version pinning**: Pin `aws4fetch` to a specific version in `package.json`. A signature algorithm change in a patch release can silently break presigning.

## Verification

```bash
# 1. Generate a presigned GET URL via the Worker and verify it works
SIGNED=$(curl -s -H "Authorization: Bearer $SESSION_TOKEN" \
  "https://api.example.com/api/download/uploads%2Fuser-123%2Ftest.pdf" | jq -r .url)

# 2. Fetch the object using the signed URL — should return 200
curl -I "$SIGNED"

# 3. Wait for expiry and retry — should return 403 (AccessDenied)
sleep 310
curl -I "$SIGNED"

# 4. Attempt to access another user's object — should return 403 from the Worker
curl -s -H "Authorization: Bearer $SESSION_TOKEN" \
  "https://api.example.com/api/download/uploads%2Fuser-456%2Fsecret.pdf" \
  | jq .error
```

## Related

- `file-upload-security-pipeline.md`
- `idor-insecure-direct-object-reference.md`
- `secrets-management-vault-dynamic-secrets.md`
- `api-key-authentication.md`

## Sources

- Cloudflare R2 presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- aws4fetch library: https://github.com/mhart/aws4fetch
- R2 API token scoping: https://developers.cloudflare.com/r2/api/tokens/
- R2 CORS configuration: https://developers.cloudflare.com/r2/buckets/cors/
