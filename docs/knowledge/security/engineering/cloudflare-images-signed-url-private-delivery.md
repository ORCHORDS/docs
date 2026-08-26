# Cloudflare Images Signed URL Private Delivery

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You store user-uploaded images in Cloudflare Images and need to serve them only to authenticated users — profile photos, medical images, identity documents, or paywalled content. Without signed URLs, any person who discovers an image URL can access it indefinitely, bypassing your application's access controls entirely. Standard Cloudflare Images delivery URLs are opaque but not access-controlled by default.

## Context

Cloudflare Images supports signed URL delivery via a per-account signing key. A Worker generates a short-lived HMAC-SHA256 signature over the image URL and an expiry timestamp; Cloudflare's image delivery infrastructure verifies the signature before serving the image. The signing key is stored as a Workers Secret (not in source or wrangler.toml). This pattern applies to both direct image URLs and flexible variant URLs.

Signed URLs are distinct from R2 pre-signed URLs — Cloudflare Images manages its own signing primitive that integrates with the Images CDN rather than R2 object storage.

---

## 1. Enabling Signed URL Delivery

In the Cloudflare dashboard: Images → Overview → Restrict access to images → Enable. This blocks unsigned requests globally for your Images account. Do this in a staging environment first — enabling it immediately breaks all existing unsigned embeds.

Once enabled, the account-level signing key is available in the dashboard under Images → Overview → Signing key. Store it as a Workers Secret:

```bash
wrangler secret put CLOUDFLARE_IMAGES_SIGNING_KEY
# Paste the key from the dashboard when prompted
```

---

## 2. Generating Signed Image URLs in a Worker

```typescript
async function signImageUrl(
  imageUrl: string,
  expirySeconds: number,
  env: Env,
): Promise<string> {
  const expiry = Math.floor(Date.now() / 1000) + expirySeconds;

  // Import the signing key
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.CLOUDFLARE_IMAGES_SIGNING_KEY),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  // Sign: HMAC-SHA256 over "<expiry><imageUrl>"
  const message = `${expiry}${imageUrl}`;
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(message),
  );

  const signatureHex = [...new Uint8Array(signature)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const url = new URL(imageUrl);
  url.searchParams.set("expiry", String(expiry));
  url.searchParams.set("sig", signatureHex);
  return url.toString();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Authenticate the requesting user first
    const session = await validateSession(request, env);
    if (!session) return new Response("Unauthorized", { status: 401 });

    const imageId = new URL(request.url).searchParams.get("imageId");
    if (!imageId) return new Response("Missing imageId", { status: 400 });

    // Validate the user is authorized to see this image (e.g., owns it)
    const authorized = await userOwnsImage(session.userId, imageId, env);
    if (!authorized) return new Response("Forbidden", { status: 403 });

    const imageUrl = `https://imagedelivery.net/${env.CF_IMAGES_ACCOUNT_HASH}/${imageId}/public`;
    const signedUrl = await signImageUrl(imageUrl, 300); // 5-minute URL

    return Response.json({ url: signedUrl });
  },
};
```

---

## 3. Scoping Signed URLs to a Specific User (Audience Binding)

A signed URL is valid for any bearer who has it. Add a user-specific claim to the URL to prevent token sharing between users:

```typescript
async function signImageUrlForUser(
  imageUrl: string,
  userId: string,
  expirySeconds: number,
  env: Env,
): Promise<string> {
  const expiry = Math.floor(Date.now() / 1000) + expirySeconds;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.CLOUDFLARE_IMAGES_SIGNING_KEY),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  // Include userId in the signed message to bind the URL to the user
  const message = `${expiry}${imageUrl}${userId}`;
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(message),
  );

  const signatureHex = [...new Uint8Array(signature)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const url = new URL(imageUrl);
  url.searchParams.set("expiry", String(expiry));
  url.searchParams.set("uid", userId);
  url.searchParams.set("sig", signatureHex);
  return url.toString();
}
```

Note: this extended signature is validated by a Workers middleware sitting in front of Cloudflare Images delivery (via a Worker route on `imagedelivery.net`), not by Cloudflare's native signed-URL verification, which uses only `expiry` and `sig`. For strict per-user binding, proxy image delivery through your own Worker domain.

---

## 4. Proxying Image Delivery Through a Worker for Full Access Control

For maximum control, bypass `imagedelivery.net` URLs entirely and serve images through your own Worker, which re-fetches from Cloudflare Images using a service binding or an internal signed fetch:

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const session = await validateSession(request, env);
    if (!session) return new Response("Unauthorized", { status: 401 });

    const url = new URL(request.url);
    const imageId = url.pathname.split("/").pop();
    if (!imageId) return new Response("Not found", { status: 404 });

    const authorized = await userOwnsImage(session.userId, imageId, env);
    if (!authorized) return new Response("Forbidden", { status: 403 });

    // Fetch from Cloudflare Images using an internal signed URL
    const internalUrl = await signImageUrl(
      `https://imagedelivery.net/${env.CF_IMAGES_ACCOUNT_HASH}/${imageId}/public`,
      30, // 30-second internal fetch window
      env,
    );

    const imageResponse = await fetch(internalUrl);
    if (!imageResponse.ok) return new Response("Image fetch failed", { status: 502 });

    // Strip origin headers and set cache-control appropriate for auth'd content
    return new Response(imageResponse.body, {
      headers: {
        "Content-Type": imageResponse.headers.get("Content-Type") ?? "image/jpeg",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  },
};
```

`Cache-Control: private, no-store` prevents CDN caching of authenticated image responses.

---

## 5. Storing Image Ownership in D1

```sql
CREATE TABLE user_images (
  image_id   TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  uploaded_at INTEGER NOT NULL,
  deleted_at  INTEGER,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_user_images_user ON user_images(user_id) WHERE deleted_at IS NULL;
```

```typescript
async function userOwnsImage(
  userId: string,
  imageId: string,
  env: Env,
): Promise<boolean> {
  const row = await env.DB.prepare(
    "SELECT 1 FROM user_images WHERE image_id = ? AND user_id = ? AND deleted_at IS NULL",
  ).bind(imageId, userId).first();
  return row !== null;
}
```

---

## Anti-patterns

- **Long expiry times** — signed URLs with 24-hour or longer expiry defeat the purpose; use 5–15 minutes for browser delivery (the browser caches the image itself).
- **Including signed URLs in server-rendered HTML that is publicly cached** — if the page is cached by a CDN, the signed URL leaks to unauthenticated users; generate URLs client-side via API or use Vary headers.
- **Sharing the signing key across environments** — use separate signing keys for production and staging; rotate if a staging key is compromised.
- **Skipping application-level authorization before signing** — Cloudflare's signed-URL verification only confirms the signature is valid; it does not check whether the requesting user is allowed to see the image — your Worker must enforce that before calling `signImageUrl`.
- **Logging signed URLs** — signed URLs are credentials; scrub them from access logs and error reporting.

## Gotchas

- Enabling "Restrict access to images" at the account level is irreversible via the API — you must use the dashboard to disable it. Enable per-deliverydomain restrictions instead for granular control.
- Cloudflare Images signed URL expiry precision is one second; browser time skew can cause intermittent failures — add a 30-second clock skew buffer to the expiry time.
- Flexible variant URLs (e.g., `/width=200`) must be signed with the full variant URL including query parameters, not just the base image ID.
- Cloudflare Images is not the same as R2; images uploaded to Images cannot be accessed via R2 APIs and have their own separate `imagedelivery.net` CDN namespace.

## Verification

```bash
# Generate a signed URL and confirm delivery
TOKEN=$(curl -s -X POST https://api.example.com/images/sign?imageId=<id> \
  -H "Cookie: session=<session>")
curl -I "$(echo $TOKEN | jq -r .url)"
# Expected: HTTP/2 200

# Confirm unsigned access is rejected
curl -I "https://imagedelivery.net/<account_hash>/<image_id>/public"
# Expected: HTTP/2 403

# Confirm expired URL is rejected (wait past expiry)
sleep 310
curl -I "$(echo $TOKEN | jq -r .url)"
# Expected: HTTP/2 401 or 403
```

## Related

- `r2-presigned-url-security.md`
- `r2-object-key-enumeration-prevention.md`
- `workers-environment-variable-hygiene.md`
- `hmac-webhook-signature-rotation-zero-downtime.md`
- `idor-insecure-direct-object-reference.md`

## Sources

- Cloudflare Images — Signed URLs — https://developers.cloudflare.com/images/manage-images/serve-images/serve-private-images-using-signed-url-tokens/
- Cloudflare Workers SubtleCrypto — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- OWASP ASVS v4.0 §9.1.3 — Media Security Verification Requirements
