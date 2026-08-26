# Cloudflare Stream Direct Creator Uploads — Workers-Orchestrated Upload Flow

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need users to upload videos directly to Cloudflare Stream without the files transiting your own servers, while still enforcing per-user quotas, attaching metadata, and receiving a webhook when encoding finishes. A Worker generates a short-lived upload URL, the browser uploads directly to Stream, and a second Worker processes the post-upload webhook to update your database.

## Context

Cloudflare Stream supports two direct-upload mechanisms: **TUS** (resumable uploads for large files, used by most SDKs) and a simple **one-time upload URL** for smaller files. In both cases, your server-side Worker calls the Stream REST API to reserve an upload slot and receives a one-time URL valid for a configurable window. The browser then POSTs the file directly to `https://upload.videodelivery.net/...` without credentials. After encoding, Stream POSTed to your configured webhook URL. This eliminates bandwidth costs on your Worker and keeps video credentials off the client.

## Generating a One-Time Upload URL

```typescript
export interface Env {
  CF_ACCOUNT_ID: string;
  CF_STREAM_API_TOKEN: string;   // Scoped token with Stream:Edit permission
  DB: D1Database;
  UPLOAD_TTL_SECONDS: string;    // default "3600"
}

interface StreamDirectUploadResponse {
  result: {
    uid: string;
    uploadURL: string;
  };
  success: boolean;
  errors: Array<{ code: number; message: string }>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "POST" && new URL(request.url).pathname === "/upload/request") {
      return handleUploadRequest(request, env);
    }
    if (request.method === "POST" && new URL(request.url).pathname === "/stream/webhook") {
      return handleStreamWebhook(request, env);
    }
    return new Response("Not found", { status: 404 });
  },
};

interface UploadRequestBody {
  fileName: string;
  fileSizeBytes: number;
  userId: string;
}

async function handleUploadRequest(
  request: Request,
  env: Env
): Promise<Response> {
  // Authenticate the caller (your own auth middleware, not shown)
  const body = await request.json<UploadRequestBody>();
  const { fileName, fileSizeBytes, userId } = body;

  if (!fileName || !userId || fileSizeBytes <= 0) {
    return Response.json({ error: "Missing required fields" }, { status: 400 });
  }

  // Enforce a 4 GB per-upload limit
  const MAX_SIZE = 4 * 1024 * 1024 * 1024;
  if (fileSizeBytes > MAX_SIZE) {
    return Response.json({ error: "File too large" }, { status: 413 });
  }

  const ttl = parseInt(env.UPLOAD_TTL_SECONDS, 10) || 3600;

  const streamResponse = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/stream/direct_upload`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_STREAM_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        maxDurationSeconds: 3600,
        expiry: new Date(Date.now() + ttl * 1000).toISOString(),
        requireSignedURLs: true,
        meta: {
          name: fileName,
          userId,
        },
        allowedOrigins: ["https://your-app.example.com"],
        watermark: { uid: null }, // Set a watermark profile UID if needed
      }),
    }
  );

  if (!streamResponse.ok) {
    const err = await streamResponse.text();
    console.error("Stream API error:", err);
    return Response.json({ error: "Upload reservation failed" }, { status: 502 });
  }

  const data = await streamResponse.json<StreamDirectUploadResponse>();
  if (!data.success) {
    return Response.json({ error: data.errors[0]?.message ?? "Unknown" }, { status: 502 });
  }

  const { uid, uploadURL } = data.result;

  // Persist the pending upload record
  await env.DB.prepare(
    "INSERT INTO uploads (stream_uid, user_id, file_name, status, created_at) VALUES (?, ?, ?, 'pending', ?)"
  )
    .bind(uid, userId, fileName, new Date().toISOString())
    .run();

  return Response.json({ uploadURL, streamUid: uid, expiresInSeconds: ttl });
}
```

## TUS Resumable Upload URL for Large Files

```typescript
// For files > ~200 MB, prefer TUS so the browser can resume on network failure
async function createTusUploadUrl(
  env: Env,
  fileSizeBytes: number,
  fileName: string,
  userId: string
): Promise<{ location: string; streamUid: string }> {
  const tusResponse = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/stream?direct_user=true`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_STREAM_API_TOKEN}`,
        "Tus-Resumable": "1.0.0",
        "Upload-Length": fileSizeBytes.toString(),
        "Upload-Metadata": [
          `name ${btoa(fileName)}`,
          `requiresignedurls`,
          `userId ${btoa(userId)}`,
        ].join(","),
      },
    }
  );

  if (!tusResponse.ok || tusResponse.status !== 201) {
    throw new Error(`TUS reservation failed: ${tusResponse.status}`);
  }

  const location = tusResponse.headers.get("Location") ?? "";
  const streamUid = tusResponse.headers.get("Stream-Media-Id") ?? "";

  if (!location || !streamUid) {
    throw new Error("Missing Location or Stream-Media-Id header from TUS response");
  }

  return { location, streamUid };
}
```

## Webhook Handler for Post-Encoding Notification

```typescript
interface StreamWebhookPayload {
  uid: string;
  status: {
    state: "ready" | "error" | "inprogress";
    errorReasonCode?: string;
    errorReasonText?: string;
    pctComplete?: string;
  };
  meta: Record<string, string>;
  playback: {
    hls: string;
    dash: string;
  };
  input: {
    width: number;
    height: number;
  };
  duration: number;
}

async function handleStreamWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  // Verify webhook signature (Cloudflare signs with the Stream webhook secret)
  const signature = request.headers.get("Webhook-Signature") ?? "";
  const body = await request.text();

  const isValid = await verifyStreamSignature(
    signature,
    body,
    env.CF_STREAM_API_TOKEN
  );
  if (!isValid) {
    return new Response("Unauthorized", { status: 403 });
  }

  const payload = JSON.parse(body) as StreamWebhookPayload;
  const { uid, status, playback, duration } = payload;

  if (status.state === "ready") {
    await env.DB.prepare(
      `UPDATE uploads
         SET status = 'ready',
             playback_hls = ?,
             playback_dash = ?,
             duration_seconds = ?,
             updated_at = ?
       WHERE stream_uid = ?`
    )
      .bind(
        playback.hls,
        playback.dash,
        Math.round(duration),
        new Date().toISOString(),
        uid
      )
      .run();
  } else if (status.state === "error") {
    await env.DB.prepare(
      `UPDATE uploads SET status = 'error', error_code = ?, updated_at = ? WHERE stream_uid = ?`
    )
      .bind(status.errorReasonCode ?? "unknown", new Date().toISOString(), uid)
      .run();
  }

  return new Response("OK");
}

async function verifyStreamSignature(
  signatureHeader: string,
  body: string,
  secret: string
): Promise<boolean> {
  // Cloudflare provides time=<epoch>,sig1=<hex> format
  const parts = Object.fromEntries(
    signatureHeader.split(",").map((p) => p.split("=") as [string, string])
  );
  const timestamp = parts["time"] ?? "";
  const sig = parts["sig1"] ?? "";
  if (!timestamp || !sig) return false;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const msgBytes = new TextEncoder().encode(`${timestamp}.${body}`);
  const sigBytes = hexToBytes(sig);
  return crypto.subtle.verify("HMAC", key, sigBytes, msgBytes);
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes;
}
```

## Anti-patterns

- Proxying the video file through your Worker to forward it to Stream — this defeats the purpose of direct creator uploads and hits the 100 MB subrequest body limit.
- Storing the `CF_STREAM_API_TOKEN` in `wrangler.toml` — always use `wrangler secret put` or the Secrets Store binding; the token grants Stream:Edit on your entire account.
- Issuing upload URLs without expiry — always set `expiry` to limit the window a leaked URL can be abused.

## Gotchas

- `requireSignedURLs: true` means the viewer must obtain a signed token from your backend to watch the video; forgetting this leaves all uploaded videos publicly accessible via `videodelivery.net`.
- Stream webhooks may arrive before your D1 write in `handleUploadRequest` has replicated — use `INSERT OR IGNORE` plus an `UPDATE` in the webhook handler rather than assuming the row exists.

## Verification

```bash
# Request a one-time upload URL
curl -X POST "https://your-worker.example.com/upload/request" \
  -H "Content-Type: application/json" \
  -d '{"fileName":"test.mp4","fileSizeBytes":10485760,"userId":"u123"}'

# Upload a small test video to the returned uploadURL
VIDEO_URL="<uploadURL from above>"
curl -X POST "$VIDEO_URL" \
  -F "file=@/tmp/test.mp4"

# Confirm the D1 record is in 'pending' state
wrangler d1 execute YOUR_DB --command \
  "SELECT stream_uid, status FROM uploads ORDER BY created_at DESC LIMIT 1"

# After encoding (~1 min), check it transitions to 'ready'
# (or manually call the webhook with a mock payload in dev)
```

## Related

- `cloudflare/stream-best-practices.md`
- `cloudflare/cloudflare-d1-import-export-wrangler.md`
- `cloudflare/r2-presigned-url-cors-mobile-upload.md`

## Sources

- https://developers.cloudflare.com/stream/uploading-videos/direct-creator-uploads/
- https://developers.cloudflare.com/stream/uploading-videos/resumable-uploads/
- https://developers.cloudflare.com/stream/webhooks/
