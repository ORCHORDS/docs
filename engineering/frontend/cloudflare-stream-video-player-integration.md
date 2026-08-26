# Cloudflare Stream Video Player Integration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to embed adaptive-bitrate video in a Cloudflare Pages site, with upload handled via a
Worker, playback controlled through the Stream Player SDK, and access restricted to authenticated
users via signed tokens.

## Context
Cloudflare Stream is a managed video platform covering ingest (direct upload, URL upload, live),
storage, transcoding, and delivery via HLS/DASH. It differs from self-hosting video in R2 because
Stream handles adaptive bitrate transcoding, DRM-free signed playback URLs, analytics, and a
customisable player embed out of the box. A Pages Function issues signed Stream tokens using the
Stream Signing Key; the browser receives a short-lived token and feeds it to the Stream Player
via `stream.js`. No raw Stream credentials ever reach the client.

---

## Architecture

```
User browser
  └── GET /api/video-token?videoId=abc  →  Pages Function
        ├── verifies session cookie
        └── signs JWT using CF_STREAM_KEY_ID + CF_STREAM_KEY_PEM
              └── returns { token: "<signed-jwt>" }

User browser
  └── <stream id="<signed-jwt>"> or new Stream("<signed-jwt>", el)
        └── Cloudflare Stream CDN delivers HLS chunks
```

---

## Pages Function: Issue Signed Stream Tokens

```typescript
// functions/api/video-token.ts
import { SignJWT, importPKCS8 } from "jose"; // bundled — no external fetch

export interface Env {
  CF_STREAM_KEY_ID: string;     // from Stream > Signing Keys
  CF_STREAM_KEY_PEM: string;    // RSA private key PEM, stored as Secret
  SESSION_KV: KVNamespace;      // for session validation
}

const TOKEN_TTL_SECONDS = 60 * 60; // 1 hour

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  // 1. Validate session
  const cookie = parseCookie(request.headers.get("Cookie") ?? "");
  const sessionId = cookie["session"];
  if (!sessionId) return new Response("Unauthorized", { status: 401 });

  const session = await env.SESSION_KV.get(`session:${sessionId}`);
  if (!session) return new Response("Unauthorized", { status: 401 });

  // 2. Extract requested video ID
  const url = new URL(request.url);
  const videoId = url.searchParams.get("videoId");
  if (!videoId || !/^[a-f0-9]{32}$/.test(videoId)) {
    return new Response("Bad Request", { status: 400 });
  }

  // 3. Sign a Stream JWT
  const privateKey = await importPKCS8(env.CF_STREAM_KEY_PEM, "RS256");

  const token = await new SignJWT({ sub: videoId })
    .setProtectedHeader({ alg: "RS256", kid: env.CF_STREAM_KEY_ID })
    .setIssuedAt()
    .setExpirationTime(`${TOKEN_TTL_SECONDS}s`)
    .sign(privateKey);

  return Response.json(
    { token, expiresIn: TOKEN_TTL_SECONDS },
    {
      headers: {
        "Cache-Control": "private, no-store",
        "Content-Type": "application/json",
      },
    }
  );
};

function parseCookie(header: string): Record<string, string> {
  return Object.fromEntries(
    header.split(";").map((c) => {
      const [k, ...v] = c.trim().split("=");
      return [k, decodeURIComponent(v.join("="))];
    })
  );
}
```

---

## Embed: Stream Player Web Component

Cloudflare Stream ships a custom element `<stream>` via `stream.cloudflare.com/embed/sdk.js`.
Since the artifact CSP blocks external scripts, use it in a standard HTML page (not an artifact):

```html
<!-- public/watch.html or a server-rendered template -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Watch</title>
  <script src="https://embed.cloudflarestream.com/embed/sdk.latest.js" defer></script>
  <style>
    .stream-wrapper { position: relative; padding-top: 56.25%; /* 16:9 */ }
    .stream-wrapper stream { position: absolute; inset: 0; width: 100%; height: 100%; }
  </style>
</head>
<body>
  <div class="stream-wrapper">
    <!-- `src` is populated by JS after fetching the signed token -->
    <stream
      id="player"
      controls
      preload="metadata"
      poster=""
    ></stream>
  </div>

  <script type="module">
    const videoId = new URLSearchParams(location.search).get("v");
    if (!videoId) throw new Error("Missing video ID");

    const res = await fetch(`/api/video-token?videoId=${encodeURIComponent(videoId)}`);
    if (!res.ok) { document.body.textContent = "Not authorised."; throw new Error(); }

    const { token } = await res.json();
    document.getElementById("player").setAttribute("src", token);
  </script>
</body>
</html>
```

---

## Stream Player SDK (Programmatic Control)

```typescript
// src/lib/streamPlayer.ts
// Import type only — the actual Stream class is loaded by embed/sdk.latest.js
declare class Stream {
  constructor(token: string, el: HTMLElement): Stream;
  play(): void;
  pause(): void;
  readonly currentTime: number;
  readonly duration: number;
  volume: number;
  muted: boolean;
  addEventListener(event: string, handler: EventListener): void;
  removeEventListener(event: string, handler: EventListener): void;
}

declare const window: Window & { Stream: typeof Stream };

export async function mountStreamPlayer(
  container: HTMLElement,
  videoId: string
): Promise<Stream> {
  // Fetch signed token from our Pages Function
  const res = await fetch(`/api/video-token?videoId=${encodeURIComponent(videoId)}`);
  if (!res.ok) throw new Error(`Token fetch failed: ${res.status}`);
  const { token } = await res.json() as { token: string };

  // Stream SDK must be loaded — await custom element upgrade
  await customElements.whenDefined("stream");

  const player = new window.Stream(token, container);

  // Refresh token before expiry (55 min)
  const REFRESH_MS = 55 * 60 * 1000;
  let refreshTimer = setTimeout(async () => {
    const refreshRes = await fetch(`/api/video-token?videoId=${encodeURIComponent(videoId)}`);
    if (refreshRes.ok) {
      const { token: newToken } = await refreshRes.json() as { token: string };
      // Re-mount with new token (Stream SDK requires re-init for token rotation)
      container.innerHTML = "";
      await mountStreamPlayer(container, videoId);
    }
  }, REFRESH_MS);

  // Expose cleanup
  (player as any)._clearRefresh = () => clearTimeout(refreshTimer);

  return player;
}
```

---

## Upload: TUS Direct Creator Upload

Cloudflare Stream supports TUS resumable uploads. Issue a one-time upload URL from a Worker,
then handle the upload in the browser via `tus-js-client`:

```typescript
// functions/api/upload-url.ts
export const onRequestPost: PagesFunction<Env> = async ({ env }) => {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/stream?direct_user=true`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_STREAM_TOKEN}`,
        "Tus-Resumable": "1.0.0",
        "Upload-Length": "0", // unknown length — use Upload-Defer-Length: 1
        "Upload-Defer-Length": "1",
        "Upload-Metadata": "maxDurationSeconds 3600",
      },
    }
  );

  const uploadUrl = res.headers.get("Location");
  const streamMediaId = res.headers.get("stream-media-id");

  if (!uploadUrl || !streamMediaId) {
    return new Response("Failed to create upload URL", { status: 500 });
  }

  return Response.json({ uploadUrl, streamMediaId });
};
```

```typescript
// Browser — src/lib/videoUpload.ts
import * as tus from "tus-js-client";

export async function uploadVideo(
  file: File,
  onProgress: (pct: number) => void
): Promise<string> {
  const { uploadUrl, streamMediaId } = await fetch("/api/upload-url", { method: "POST" })
    .then((r) => r.json()) as { uploadUrl: string; streamMediaId: string };

  await new Promise<void>((resolve, reject) => {
    const upload = new tus.Upload(file, {
      uploadUrl,
      chunkSize: 50 * 1024 * 1024, // 50 MB chunks
      retryDelays: [0, 3000, 5000, 10000, 20000],
      onProgress(uploaded, total) {
        onProgress(Math.round((uploaded / total) * 100));
      },
      onSuccess: () => resolve(),
      onError: (err) => reject(err),
    });
    upload.start();
  });

  return streamMediaId; // store this to generate playback tokens later
}
```

---

## Anti-patterns
- Returning the Stream signing key PEM to the client — tokens must be minted server-side
- Setting very long token expiry (e.g. 30 days) — use 1–2 hour expiry and refresh before expiry
- Embedding the `<stream>` element with a direct video ID (not a signed token) on authenticated pages — any user with the source can share the ID
- Not specifying `poster` on the `<stream>` element — causes a blank black frame before the first frame loads
- Skipping the 16:9 aspect-ratio wrapper — the player defaults to `height: 0` without explicit dimensions

## Gotchas
- Cloudflare Stream signing keys are account-scoped, not zone-scoped; one key pair can sign tokens for all videos in the account
- `jose` must be bundled — it is not available as a Cloudflare global; add it via npm and bundle with Wrangler
- The `stream-media-id` header in the TUS response is the video ID; the upload URL is single-use
- Videos are not immediately available for playback after TUS upload completion — Stream transcodes asynchronously; poll the video status API or use Stream Webhooks
- `customElements.whenDefined("stream")` rejects if the SDK script fails to load; wrap in a try/catch with a fallback `<video>` element

## Verification
```bash
# Check Stream video status (ready_to_stream must be true)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/stream/$VIDEO_ID" \
  -H "Authorization: Bearer $CF_STREAM_TOKEN" | jq '.result.readyToStream'

# Decode a signed token to inspect claims
echo "$SIGNED_TOKEN" | cut -d. -f2 | base64 -d | jq .
# Expect: { sub: "<videoId>", iat: ..., exp: ... }

# Fetch a playback token via the Pages Function
curl -s "https://yoursite.pages.dev/api/video-token?videoId=$VIDEO_ID" \
  -H "Cookie: session=$SESSION_ID" | jq .token

# List signing keys
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/stream/keys" \
  -H "Authorization: Bearer $CF_STREAM_TOKEN" | jq '.result[].id'
```

## Related
- `video-autoplay-mobile-restrictions-hls.md`
- `cloudflare-r2-presigned-upload-frontend.md`
- `websocket-durable-objects-realtime-ui.md`
- `cloudflare-pages-functions-session-validation-middleware.md`
- `file-upload-ux-chunked-resumable.md`

## Sources
- https://developers.cloudflare.com/stream/
- https://developers.cloudflare.com/stream/viewing-videos/securing-your-stream/
- https://developers.cloudflare.com/stream/uploading-videos/direct-creator-uploads/
- https://developers.cloudflare.com/stream/getting-analytics/
- https://github.com/tus/tus-js-client
