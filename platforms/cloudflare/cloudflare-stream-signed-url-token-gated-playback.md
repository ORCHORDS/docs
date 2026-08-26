# Cloudflare Stream: Signed URLs and Token-Gated Playback

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have premium or private video content on Cloudflare Stream and need to ensure that only
authenticated users can watch it. Public HLS/DASH manifests are fine for open content, but
embedding a raw stream URL in a page exposes it permanently — anyone who extracts it can share
or download the content indefinitely.

Stream's signed URL feature restricts playback to holders of a short-lived token issued by
your Worker, with optional viewer-binding to prevent token sharing.

## Context

Every Stream video has a unique `uid`. By default, playback URLs are public if the video is
not set to `requireSignedURLs`. Once that flag is enabled on a video:

- Direct playback at `https://customer-<code>.cloudflarestream.com/<uid>/manifest/video.m3u8`
  returns `401 Unauthorized`.
- Playback is only possible through a token-signed URL or the signed iframe embed.

Tokens are signed JWTs using an RSA or EC key pair generated in the Stream dashboard or API.
The private key never leaves your Worker (or Secrets Store); the public key is registered with
Cloudflare for verification.

Token fields of interest: `exp` (expiry), `nbf` (not-before), `sub` (video UID), `accessRules`
(IP, country, or any restrictions), and `downloadable` (whether the MP4 download link is
available). Tokens are verified at the edge; your Worker is not in the hot path during playback.

## Enabling Signed URLs on a Video

```typescript
// src/require-signed.ts  — run once per video at upload time or via admin endpoint
interface Env {
  CF_ACCOUNT_ID: string;
  CF_STREAM_API_TOKEN: string; // needs Stream:Edit permission
}

async function requireSignedUrls(videoUid: string, env: Env): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/stream/${videoUid}`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_STREAM_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ requireSignedURLs: true }),
  });

  if (!res.ok) {
    const err = await res.json<{ errors: { message: string }[] }>();
    throw new Error(`Stream API error: ${err.errors[0]?.message}`);
  }
}
```

## Generating a Signed Playback Token in a Worker

```typescript
// src/sign-token.ts
interface Env {
  CF_ACCOUNT_ID: string;
  STREAM_KEY_ID: string;         // key ID from Stream dashboard
  STREAM_PRIVATE_KEY: string;    // PEM private key stored as a Secret
}

// Cache the imported key across requests in module scope (safe — read-only)
let signingKey: CryptoKey | null = null;

async function getSigningKey(pemPrivate: string): Promise<CryptoKey> {
  if (signingKey) return signingKey;

  const pemContents = pemPrivate
    .replace(/<redacted-private-key>|\n/g, "");
  const keyData = Uint8Array.from(atob(pemContents), (c) => c.charCodeAt(0));

  signingKey = await crypto.subtle.importKey(
    "pkcs8",
    keyData,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return signingKey;
}

function base64url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function signStreamToken(
  videoUid: string,
  ttlSeconds: number,
  env: Env,
  options: { downloadable?: boolean; allowedCountries?: string[] } = {},
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const key = await getSigningKey(env.STREAM_PRIVATE_KEY);

  const header = { alg: "RS256", kid: env.STREAM_KEY_ID };
  const payload: Record<string, unknown> = {
    sub: videoUid,
    kid: env.STREAM_KEY_ID,
    exp: now + ttlSeconds,
    nbf: now - 1,                // 1-second grace for clock skew
  };

  if (options.downloadable !== undefined) payload["downloadable"] = options.downloadable;
  if (options.allowedCountries?.length) {
    payload["accessRules"] = [
      { type: "ip.geoip.country", country: options.allowedCountries, action: "allow" },
      { type: "any", action: "block" },
    ];
  }

  const enc = (obj: unknown) => base64url(new TextEncoder().encode(JSON.stringify(obj)));
  const signingInput = `${enc(header)}.${enc(payload)}`;
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(signingInput));

  return `${signingInput}.${base64url(sig)}`;
}
```

## Issuing Tokens in a Gated API Endpoint

```typescript
// src/index.ts
import { signStreamToken } from "./sign-token";

interface Env {
  CF_ACCOUNT_ID: string;
  STREAM_KEY_ID: string;
  STREAM_PRIVATE_KEY: string;
  // your auth layer — e.g. a KV namespace of valid session tokens
  SESSIONS: KVNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (new URL(req.url).pathname !== "/api/stream-token") {
      return new Response("Not found", { status: 404 });
    }

    // 1. Validate caller's session
    const sessionToken = req.headers.get("Authorization")?.replace("Bearer ", "");
    if (!sessionToken) return new Response("Unauthorized", { status: 401 });

    const userId = await env.SESSIONS.get(sessionToken);
    if (!userId) return new Response("Unauthorized", { status: 401 });

    // 2. Determine which video this user may watch (your own entitlement logic)
    const { videoUid } = await req.json<{ videoUid: string }>();
    const entitled = await checkEntitlement(userId, videoUid); // your DB call
    if (!entitled) return new Response("Forbidden", { status: 403 });

    // 3. Issue a short-lived playback token (15 minutes)
    const token = await signStreamToken(videoUid, 900, env, { downloadable: false });

    return Response.json({
      token,
      playerUrl: `https://customer-<subdomain>.cloudflarestream.com/${token}/iframe`,
      manifestUrl: `https://customer-<subdomain>.cloudflarestream.com/${token}/manifest/video.m3u8`,
    });
  },
};

async function checkEntitlement(_userId: string, _videoUid: string): Promise<boolean> {
  // stub — replace with your D1/KV/external DB lookup
  return true;
}
```

## Embedding the Signed Player

```html
<!-- In your front-end — token fetched from the gated API above -->
<stream

  controls
  preload="metadata"
></stream>
<script src="https://embed.cloudflarestream.com/embed/sdk.latest.js" defer></script>
```

For custom players (Video.js, HLS.js), use the `manifestUrl` returned from the API. Tokens
work with both the iframe embed and direct manifest URLs — the same JWT governs both.

## Token Refresh Before Expiry

```typescript
// client-side — refresh the token 60 s before it expires
async function maintainToken(videoUid: string, playerEl: HTMLElement) {
  while (true) {
    const { token, expiresAt } = await fetchToken(videoUid); // your API call
    playerEl.setAttribute("src", token);

    const refreshIn = (expiresAt - Date.now() / 1000 - 60) * 1000;
    await new Promise((r) => setTimeout(r, Math.max(refreshIn, 0)));
  }
}
```

## Anti-patterns

- Generating tokens server-side with `exp` more than 1 hour out — a leaked token stays valid
  for that full window; 15–30 minutes is the recommended maximum.
- Serving the private key to the browser — token signing must happen in a Worker or secure
  backend; never expose the PEM.
- Skipping `requireSignedURLs: true` on the video — the signed token is silently ignored and
  the video remains public.
- Re-using the same token across multiple concurrent viewers — Cloudflare does not enforce
  single-viewer tokens today, but accessRules (IP binding) provide similar protection.

## Gotchas

- The `kid` field in the JWT header must exactly match the key ID registered in Stream; a
  mismatch returns `401` with no additional detail.
- Key pairs created in the Stream dashboard are RSA (PKCS#8); if you generate your own EC key
  pair you must register it via the API, not the dashboard.
- `nbf` skew: edge PoPs may differ from your Worker's clock by a few seconds; set `nbf` 1–5
  seconds in the past to avoid race conditions at token issuance.
- The `customer-<subdomain>` hostname is account-specific; find it under Stream settings or
  in the video details API response as `playback.hls`.

## Verification

```bash
# Confirm the video requires signed URLs
curl -s -H "Authorization: Bearer $CF_STREAM_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/stream/$VIDEO_UID" \
  | jq '.result.requireSignedURLs'

# Confirm a public manifest returns 401
curl -I "https://customer-<subdomain>.cloudflarestream.com/$VIDEO_UID/manifest/video.m3u8"
# HTTP/2 401

# Confirm a signed manifest returns 200
TOKEN=$(curl -s -X POST https://your-worker.example.com/api/stream-token \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -d "{\"videoUid\":\"$VIDEO_UID\"}" | jq -r '.token')
curl -I "https://customer-<subdomain>.cloudflarestream.com/$TOKEN/manifest/video.m3u8"
# HTTP/2 200
```

## Related

- `stream-best-practices.md`
- `cloudflare-stream-direct-creator-uploads.md`
- `cloudflare-stream-live-workers-webhook-integration.md`
- `stream-adaptive-bitrate-mobile-hls-dash.md`
- `cloudflare-access-jwt-validation.md`

## Sources

- https://developers.cloudflare.com/stream/viewing-videos/securing-your-stream/
- https://developers.cloudflare.com/stream/viewing-videos/using-own-player/
- https://developers.cloudflare.com/stream/reference/signed-urltokens/
