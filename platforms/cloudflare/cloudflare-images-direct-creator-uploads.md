# Cloudflare Images Direct Creator Uploads

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want users to upload images directly from their browser or mobile app to Cloudflare Images without the file ever touching your origin server. Using a server-side proxy for uploads adds latency, increases egress costs, and creates a bottleneck. You need a short-lived, single-use upload URL that your backend generates and your frontend consumes — the same pattern as Cloudflare Stream's direct creator uploads.

## Context

Cloudflare Images exposes a `/direct_upload` endpoint on the API. Your backend calls it with your API token and receives a one-time `uploadURL` plus an image `id`. Your frontend then `POST`s the file directly to that URL as `multipart/form-data`. After the upload, the image is available under the assigned `id` via the standard delivery URL. The upload URL expires after one hour and accepts exactly one upload. This flow works from browsers, React Native apps, and mobile clients without exposing your Cloudflare API token.

---

## Backend: Generating a One-Time Upload URL (Workers)

```typescript
// upload-token-worker/src/index.ts
interface Env {
  CF_ACCOUNT_ID: string;  // from secret
  CF_IMAGES_TOKEN: string; // scoped to "Cloudflare Images:Edit"
}

interface DirectUploadResponse {
  result: {
    id: string;
    uploadURL: string;
  };
  success: boolean;
  errors: { code: number; message: string }[];
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    // Optional: validate the caller is authenticated (JWT, session cookie, etc.)
    // const user = await verifySession(req);
    // if (!user) return new Response('Unauthorized', { status: 401 });

    const body = await req.json<{ metadata?: Record<string, string>; requireSignedURLs?: boolean }>();

    const apiRes = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/images/v2/direct_upload`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.CF_IMAGES_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          requireSignedURLs: body.requireSignedURLs ?? false,
          metadata: body.metadata ?? {},
        }),
      }
    );

    const data = await apiRes.json<DirectUploadResponse>();

    if (!data.success) {
      return Response.json({ error: data.errors[0]?.message ?? 'Unknown error' }, { status: 502 });
    }

    return Response.json({
      imageId: data.result.id,
      uploadURL: data.result.uploadURL,
      expiresIn: 3600, // seconds
    });
  },
};
```

Scope the API token to **Cloudflare Images:Edit** on the specific account only — it does not need Zone permissions.

---

## Frontend: Uploading Directly to the One-Time URL

```typescript
// Browser / React Native client

async function uploadImage(file: File | Blob, metadata?: Record<string, string>) {
  // 1. Get a one-time upload URL from your backend
  const tokenRes = await fetch('/api/upload-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ metadata }),
  });
  const { imageId, uploadURL } = await tokenRes.json<{
    imageId: string;
    uploadURL: string;
  }>();

  // 2. Upload directly to Cloudflare Images — no API token required
  const form = new FormData();
  form.append('file', file);

  const uploadRes = await fetch(uploadURL, {
    method: 'POST',
    body: form,
    // No Authorization header — the URL itself is the credential
  });

  if (!uploadRes.ok) {
    const err = await uploadRes.json();
    throw new Error(`Upload failed: ${JSON.stringify(err)}`);
  }

  return imageId; // use to construct delivery URL
}

// Delivery URL (public variant)
function imageUrl(imageId: string, variant = 'public'): string {
  return `https://imagedelivery.net/${ACCOUNT_HASH}/${imageId}/${variant}`;
}
```

---

## Post-Upload Webhook: Confirming Image Processing

Cloudflare Images processes uploaded files asynchronously (format conversion, variant generation). Poll the image status or configure a Cloudflare Worker as a Tail Worker triggered by the Images platform (not yet GA) — for now, use a short polling strategy:

```typescript
// Confirm image is ready before returning the delivery URL to the client
async function waitForImage(
  imageId: string,
  env: Env,
  maxAttempts = 10,
  delayMs = 500
): Promise<boolean> {
  for (let i = 0; i < maxAttempts; i++) {
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/images/v1/${imageId}`,
      { headers: { Authorization: `Bearer ${env.CF_IMAGES_TOKEN}` } }
    );

    if (res.status === 404) {
      // Not processed yet — wait
      await new Promise((r) => setTimeout(r, delayMs));
      continue;
    }

    const data = await res.json<{ result: { draft: boolean } }>();
    if (!data.result.draft) return true; // image is live

    await new Promise((r) => setTimeout(r, delayMs));
  }

  return false;
}
```

An image returned with `"draft": true` is still processing; variants are not yet available.

---

## Requiring Signed Delivery URLs on Upload

If the image is private (e.g., user profile photos behind authentication), set `requireSignedURLs: true` in the `direct_upload` request. Every subsequent delivery request must include a signed URL token:

```typescript
// Generate a signed delivery URL in a Worker (server-side only)
async function signedImageUrl(
  imageId: string,
  variant: string,
  env: Env,
  expirySeconds = 3600
): Promise<string> {
  const expiry = Math.floor(Date.now() / 1000) + expirySeconds;

  const encoder = new TextEncoder();
  const keyData = encoder.encode(env.CF_IMAGES_SIGNING_KEY);
  const key = await crypto.subtle.importKey(
    'raw', keyData, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );

  const message = `${imageId}/${variant}?exp=${expiry}`;
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(message));
  const sig = btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  return `https://imagedelivery.net/${env.CF_ACCOUNT_HASH}/${imageId}/${variant}?exp=${expiry}&sig=${sig}`;
}
```

`CF_IMAGES_SIGNING_KEY` is found under **Images → Keys** in the dashboard and stored as a Worker secret.

---

## Attaching Metadata at Upload Time

Metadata set during `direct_upload` is searchable via the Images API and useful for correlating images to your application's data model:

```typescript
// In the backend Worker — pass metadata to direct_upload
body: JSON.stringify({
  requireSignedURLs: false,
  metadata: {
    userId: user.id,
    purpose: 'avatar',
    uploadedAt: new Date().toISOString(),
  },
}),
```

Metadata keys and values are strings; total metadata size must be under 1 024 bytes. Retrieve it later:

```typescript
const info = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/images/v1/${imageId}`,
  { headers: { Authorization: `Bearer ${env.CF_IMAGES_TOKEN}` } }
);
const { result } = await info.json<{ result: { metadata: Record<string, string> } }>();
console.log(result.metadata.userId);
```

---

## Anti-patterns

- **Exposing `CF_IMAGES_TOKEN` to the browser** — a token that can call `direct_upload` can also delete or list all images; always generate the one-time URL server-side.
- **Reusing an upload URL** — the URL is single-use. A second upload to the same URL returns `400`. Generate a fresh URL per upload attempt.
- **Serving images from the API domain** — delivery must go through `imagedelivery.net` or your custom domain, not `api.cloudflare.com`.
- **Skipping the `draft` check** — returning the delivery URL before the image exits draft state causes 404s for the user.

---

## Gotchas

- The upload URL expires in **exactly 1 hour** from generation — no way to extend it. If your upload flow is long-running (large files, slow connections), generate the URL as late as possible.
- File size limit is **10 MB** per image. Larger files require the Images API's server-side upload endpoint (your origin downloads the file).
- Accepted formats: JPEG, PNG, GIF, WebP, SVG, HEIC, AVIF. PDFs and video files are rejected.
- `requireSignedURLs` cannot be toggled after upload via the direct upload flow — it is set at creation time. To change it, update the image via the `/images/v1/{id}` PATCH endpoint.
- `imagedelivery.net` is blocked in some enterprise networks that allowlist by domain; custom domain delivery (`cdn.example.com` via CNAME) is more reliable in those environments.

---

## Verification

```bash
# 1. Generate a one-time upload URL
curl -X POST https://your-worker.example.com/api/upload-token \
  -H "Content-Type: application/json" \
  -d '{"metadata":{"test":"true"}}' | jq .

# 2. Upload a test image to the returned uploadURL
curl -X POST "$UPLOAD_URL" \
  -F "file=@/path/to/test.jpg"

# 3. Confirm image is live
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/images/v1/$IMAGE_ID" \
  -H "Authorization: Bearer $CF_IMAGES_TOKEN" | jq '.result.draft'
# Expected: false

# 4. Verify delivery
curl -I "https://imagedelivery.net/$ACCOUNT_HASH/$IMAGE_ID/public"
# Expected: HTTP/2 200
```

---

## Related

- `cloudflare-images-flexible-variants-workers.md`
- `cloudflare-images-transform-urls-variants.md`
- `cloudflare-stream-direct-creator-uploads.md`
- `r2-presigned-url-cors-mobile-upload.md`
- `images-best-practices.md`

---

## Sources

- Cloudflare Images — Direct Creator Uploads: https://developers.cloudflare.com/images/upload-images/direct-creator-upload/
- Cloudflare Images — Signed URLs: https://developers.cloudflare.com/images/manage-images/serve-images/serve-private-images-using-signed-url-tokens/
- Cloudflare Images — Metadata: https://developers.cloudflare.com/images/manage-images/edit-images/
- Images API reference: https://developers.cloudflare.com/api/operations/cloudflare-images-create-authenticated-direct-upload-url-v-2
