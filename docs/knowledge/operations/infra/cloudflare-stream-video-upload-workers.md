# Cloudflare Stream + Workers: TUS Upload, Signed URLs, Webhooks, and HLS Serving

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to accept large video uploads from end-users, process them through Cloudflare Stream for adaptive-bitrate transcoding, restrict playback to authenticated users, and be notified when a video is ready. This article covers the full lifecycle: TUS upload initiation via a Worker, signed playback URL generation, Stream webhook handling, and serving HLS with access control.

## Context

- Cloudflare Stream (separate subscription, per-minute billing)
- Workers handle auth, URL signing, and webhook ingestion
- TUS protocol for resumable uploads (clients use tus-js-client or similar)
- HLS manifest served at `https://videodelivery.net/<UID>/manifest/video.m3u8`
- Stack: TypeScript Workers, Cloudflare Stream API, Workers Secrets, Wrangler v3

---

## Section 1: Initiate a TUS Upload from a Worker

The client requests an upload URL from your Worker; the Worker calls Stream's API to create the upload slot, then returns the TUS endpoint to the client.

```typescript
// src/upload-handler.ts

const STREAM_API = "https://api.cloudflare.com/client/v4/accounts";

export interface Env {
  CF_ACCOUNT_ID: string; // Wrangler secret
  CF_STREAM_TOKEN: string; // Wrangler secret — Stream-scoped API token
  WEBHOOK_SECRET: string; // Shared secret for webhook validation
}

interface TUSUploadResponse {
  result: {
    uid: string;
    uploadURL: string;
    scheduledDeletion?: string;
  };
  success: boolean;
  errors: Array<{ message: string }>;
}

export async function handleUploadRequest(
  request: Request,
  env: Env
): Promise<Response> {
  // Expect client to send: { fileName: string, fileSizeBytes: number, userId: string }
  const body = await request.json() as {
    fileName: string;
    fileSizeBytes: number;
    userId: string;
  };

  if (!body.fileSizeBytes || body.fileSizeBytes > 10 * 1024 * 1024 * 1024) {
    return new Response("Invalid file size (max 10 GB)", { status: 400 });
  }

  const res = await fetch(
    `${STREAM_API}/${env.CF_ACCOUNT_ID}/stream?direct_user=true`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_STREAM_TOKEN}`,
        // TUS protocol requires these headers when creating upload slot
        "Tus-Resumable": "1.0.0",
        "Upload-Length": String(body.fileSizeBytes),
        "Upload-Metadata": [
          `name ${btoa(body.fileName)}`,
          `userId ${btoa(body.userId)}`,
          `requireSignedURLs true`,
        ].join(","),
      },
      body: "", // Empty body for slot creation
    }
  );

  if (!res.ok) {
    const err = await res.text();
    return new Response(`Stream API error: ${err}`, { status: 502 });
  }

  // Stream returns upload URL in the Location header for TUS
  const uploadURL = res.headers.get("Location");
  const streamMediaId = res.headers.get("stream-media-id");

  if (!uploadURL || !streamMediaId) {
    return new Response("Missing Location or stream-media-id header", { status: 502 });
  }

  return Response.json({
    uploadURL, // Client sends TUS chunks here directly
    videoUID: streamMediaId,
  });
}
```

---

## Section 2: Generate Signed Playback URLs

```typescript
// src/signed-url.ts
// Stream uses RS256 JWT for signed URLs; sign with your Stream signing key pair.

interface StreamSigningKey {
  id: string; // Key ID — include as `kid` in JWT header
  pem: string; // RSA private key PEM
}

async function importSigningKey(pem: string): Promise<CryptoKey> {
  // Strip PEM headers and decode
  const b64 = pem
    .replace(/<redacted-private-key>/, "")
    .replace(/\s/g, "");
  const der = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

  return crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );
}

function base64url(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

export async function generateSignedStreamURL(
  videoUID: string,
  signingKey: StreamSigningKey,
  expirySeconds = 3600
): Promise<string> {
  const key = await importSigningKey(signingKey.pem);

  const header = base64url(
    new TextEncoder().encode(
      JSON.stringify({ alg: "RS256", kid: signingKey.id })
    )
  );

  const now = Math.floor(Date.now() / 1000);
  const payload = base64url(
    new TextEncoder().encode(
      JSON.stringify({
        sub: videoUID,
        kid: signingKey.id,
        exp: now + expirySeconds,
        accessRules: [
          { type: "any", action: "allow" },
        ],
      })
    )
  );

  const sigInput = new TextEncoder().encode(`${header}.${payload}`);
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, sigInput);

  const token = `${header}.${payload}.${base64url(sig)}`;

  // Return signed HLS manifest URL
  return `https://videodelivery.net/${videoUID}/manifest/video.m3u8?token=${token}`;
}

// Usage in fetch handler:
export async function handlePlaybackRequest(
  request: Request,
  env: Env & { STREAM_SIGNING_KEY_ID: string; STREAM_SIGNING_KEY_PEM: string }
): Promise<Response> {
  const url = new URL(request.url);
  const videoUID = url.searchParams.get("uid");
  if (!videoUID) return new Response("Missing uid", { status: 400 });

  const signedURL = await generateSignedStreamURL(
    videoUID,
    { id: env.STREAM_SIGNING_KEY_ID, pem: env.STREAM_SIGNING_KEY_PEM },
    7200 // 2-hour expiry
  );

  return Response.json({ hlsURL: signedURL });
}
```

---

## Section 3: Webhook Handler (Video Ready Notification)

```typescript
// src/webhook-handler.ts
// Cloudflare Stream POSTs to your webhook URL when video state changes.

interface StreamWebhookPayload {
  uid: string;
  status: {
    state: "pendingupload" | "waiting" | "processing" | "ready" | "error";
    errorReasonCode?: string;
    errorReasonText?: string;
  };
  meta: Record<string, string>;
  created: string;
  modified: string;
  duration: number;
  input: { width: number; height: number };
  playback: { hls: string; dash: string };
}

export async function handleWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  // Validate webhook signature
  const signature = request.headers.get("Webhook-Signature");
  const rawBody = await request.text();

  if (!signature || !await verifyWebhookSignature(rawBody, signature, env.WEBHOOK_SECRET)) {
    return new Response("Unauthorized", { status: 401 });
  }

  const payload: StreamWebhookPayload = JSON.parse(rawBody);

  if (payload.status.state === "ready") {
    console.log(`Video ready: ${payload.uid}, duration: ${payload.duration}s`);
    // Notify your app DB, send email, update KV, etc.
    // e.g., await env.DB.prepare("UPDATE videos SET status=? WHERE uid=?").bind("ready", payload.uid).run();
  } else if (payload.status.state === "error") {
    console.error(`Video error: ${payload.uid} — ${payload.status.errorReasonText}`);
  }

  return new Response("OK", { status: 200 });
}

async function verifyWebhookSignature(
  body: string,
  signatureHeader: string,
  secret: string
): Promise<boolean> {
  // Header format: "time=<ts>,sig1=<hex>"
  const parts = Object.fromEntries(
    signatureHeader.split(",").map((p) => p.split("=") as [string, string])
  );
  const timestamp = parts["time"];
  const receivedSig = parts["sig1"];

  const keyData = new TextEncoder().encode(secret);
  const msgData = new TextEncoder().encode(`${timestamp}.${body}`);

  const key = await crypto.subtle.importKey(
    "raw", keyData, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, msgData);
  const computed = Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0")).join("");

  return computed === receivedSig;
}
```

---

## Anti-patterns

- Do not proxy video bytes through your Worker — return the signed URL to the client and let Cloudflare Stream serve HLS directly.
- Do not embed permanent API tokens in client-side code; always generate signed playback JWTs server-side.
- Do not skip webhook signature verification — anyone can POST to your webhook endpoint.
- Do not set very long JWT expiry on signed URLs for sensitive content; prefer 1-2 hours with refresh.

## Gotchas

- Stream signing keys must be created via the Stream API (`POST /accounts/<id>/stream/keys`); they cannot be arbitrary RSA keys.
- `Upload-Metadata` values must be base64-encoded without padding issues — use `btoa()` carefully with unicode file names.
- TUS upload slots expire if the upload isn't started within a short window; re-request the URL if the client restarts.
- `direct_user=true` is required when the client uploads directly (not via your Worker); omit it only if you are proxying bytes.
- Webhook delivery is not guaranteed exactly-once; make your handler idempotent.

## Verification

```bash
# Check video status
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/stream/${VIDEO_UID}" \
  -H "Authorization: Bearer ${CF_STREAM_TOKEN}" | jq '.result.status'

# List signing keys
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/stream/keys" \
  -H "Authorization: Bearer ${CF_STREAM_TOKEN}" | jq '.result[] | .id'

# Set webhook URL
curl -s -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/stream/webhook" \
  -H "Authorization: Bearer ${CF_STREAM_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"notificationUrl": "https://platform.example.com/webhooks/stream"}' | jq .

# Verify HLS playback (after video is ready)
curl -I "https://videodelivery.net/${VIDEO_UID}/manifest/video.m3u8?token=<redacted-secret>
```

## Related

- `documentation/docs/policies/infra/workers-for-platforms-dispatch-namespace.md`
- `documentation/docs/policies/infra/workers-waiting-room-queue-bypass-kv.md`

## Sources

- https://developers.cloudflare.com/stream/uploading-videos/upload-video-file/
- https://developers.cloudflare.com/stream/viewing-videos/securing-your-stream/
- https://developers.cloudflare.com/stream/manage-video-library/using-webhooks/
- https://developers.cloudflare.com/stream/viewing-videos/using-the-stream-player/
