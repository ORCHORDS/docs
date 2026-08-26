# Cloudflare Stream Live Workers Webhook Integration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project / example.com supports live ephemeral broadcasts where users stream directly from their phones. The platform needs to know instantly when a live stream goes online or ends — to create/close the live post entry in D1, push a real-time notification to viewers via Durable Object WebSocket hubs, and archive the recording to R2 when the stream ends. Cloudflare Stream emits webhook events for these lifecycle transitions, but the platform needs a Worker to receive, verify, and fanout these events within the same Cloudflare network.

## Context
Cloudflare Stream Live Inputs support RTMP and WHIP ingest. Stream emits signed webhooks (HMAC-SHA256) when a live input transitions state: `live_input.connected`, `live_input.disconnected`, and `live_input.recording.ready`. A Worker registered as the webhook endpoint can handle all three events, update D1, push WS notifications, and trigger downstream archival — all within the edge network, minimizing roundtrip latency compared to a traditional origin server webhook handler.

## Stream Live Input Configuration

Create a live input via the Stream API and register the webhook Worker as the notification URL:

```bash
# Create live input
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/stream/live_inputs" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "meta": { "name": "example project-live-input" },
    "recording": { "mode": "automatic", "timeoutSeconds": 60 },
    "defaultCreator": "example project"
  }'

# Register the Worker webhook URL
curl -X PUT "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/stream/webhook" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notificationUrl": "https://stream-hooks.example.com/webhook"}'
```

The `notificationUrl` must be a publicly reachable HTTPS endpoint — your deployed Worker's custom domain.

## wrangler.toml for the Webhook Worker

```toml
# wrangler.toml
name = "example project-stream-hooks"
main = "src/index.ts"
compatibility_date = "2025-01-01"

routes = [{ pattern = "stream-hooks.example.com/webhook", custom_domain = true }]

[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[durable_objects.bindings]]
name = "BROADCAST_HUB"
class_name = "BroadcastHub"
script_name = "example project-realtime"   # service binding to the DO-hosting Worker

[vars]
CF_ACCOUNT_ID = "your-account-id"

# Secrets: STREAM_WEBHOOK_SECRET (from CF dashboard webhook config)
```

## Webhook Signature Verification

Cloudflare signs each Stream webhook with HMAC-SHA256 using a secret you retrieve from the webhook registration response. Verify before processing:

```typescript
// src/verify.ts
export async function verifyStreamWebhook(
  req: Request,
  secret: string
): Promise<boolean> {
  const sig = req.headers.get("Webhook-Signature");
  if (!sig) return false;

  // Format: "time=<epoch>,sig1=<hex>"
  const parts = Object.fromEntries(sig.split(",").map((p) => p.split("=")));
  const timestamp = parts["time"];
  const receivedSig = parts["sig1"];

  if (!timestamp || !receivedSig) return false;

  // Reject replays older than 5 minutes
  const age = Math.abs(Date.now() / 1000 - Number(timestamp));
  if (age > 300) return false;

  const body = await req.clone().text();
  const payload = `${timestamp}.${body}`;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const computed = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payload)
  );

  const computedHex = Array.from(new Uint8Array(computed))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Constant-time comparison
  return computedHex === receivedSig;
}
```

## Webhook Event Handling and Fanout

```typescript
// src/index.ts
import { verifyStreamWebhook } from "./verify";

export interface Env {
  DB: D1Database;
  BROADCAST_HUB: DurableObjectNamespace;
  STREAM_WEBHOOK_SECRET: string;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}

interface StreamEvent {
  action: "live_input.connected" | "live_input.disconnected" | "live_input.recording.ready";
  liveInput: {
    uid: string;
    meta: { name: string };
  };
  recording?: {
    uid: string;
    duration: number;
    playback: { hls: string; dash: string };
  };
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (req.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const valid = await verifyStreamWebhook(req, env.STREAM_WEBHOOK_SECRET);
    if (!valid) return new Response("Unauthorized", { status: 401 });

    const event = await req.json<StreamEvent>();
    ctx.waitUntil(handleStreamEvent(event, env));

    // Respond immediately — Cloudflare retries if the response is not 2xx
    return new Response(null, { status: 204 });
  },
};

async function handleStreamEvent(event: StreamEvent, env: Env): Promise<void> {
  const { action, liveInput, recording } = event;
  const liveInputUid = liveInput.uid;

  switch (action) {
    case "live_input.connected":
      await onStreamConnected(liveInputUid, env);
      break;

    case "live_input.disconnected":
      await onStreamDisconnected(liveInputUid, env);
      break;

    case "live_input.recording.ready":
      if (recording) {
        await onRecordingReady(liveInputUid, recording, env);
      }
      break;
  }
}

async function onStreamConnected(uid: string, env: Env): Promise<void> {
  // Create a live post in D1
  await env.DB.prepare(
    `INSERT INTO live_posts (live_input_uid, status, started_at)
     VALUES (?, 'live', CURRENT_TIMESTAMP)
     ON CONFLICT (live_input_uid) DO UPDATE SET status = 'live', started_at = CURRENT_TIMESTAMP`
  ).bind(uid).run();

  // Notify viewers via Durable Object WebSocket hub
  const hubId = env.BROADCAST_HUB.idFromName("global-notifications");
  const hub = env.BROADCAST_HUB.get(hubId);
  await hub.fetch("https://internal/broadcast", {
    method: "POST",
    body: JSON.stringify({ type: "stream_started", liveInputUid: uid }),
  });
}

async function onStreamDisconnected(uid: string, env: Env): Promise<void> {
  await env.DB.prepare(
    `UPDATE live_posts SET status = 'ended', ended_at = CURRENT_TIMESTAMP
     WHERE live_input_uid = ?`
  ).bind(uid).run();

  const hubId = env.BROADCAST_HUB.idFromName("global-notifications");
  const hub = env.BROADCAST_HUB.get(hubId);
  await hub.fetch("https://internal/broadcast", {
    method: "POST",
    body: JSON.stringify({ type: "stream_ended", liveInputUid: uid }),
  });
}

async function onRecordingReady(
  uid: string,
  recording: NonNullable<StreamEvent["recording"]>,
  env: Env
): Promise<void> {
  // Attach recording metadata to the post
  await env.DB.prepare(
    `UPDATE live_posts
     SET recording_uid = ?, hls_url = ?, duration_sec = ?, status = 'archived'
     WHERE live_input_uid = ?`
  )
    .bind(recording.uid, recording.playback.hls, recording.duration, uid)
    .run();
}
```

## Embedding the Player in the Social Feed

Once `recording.ready` fires, the HLS URL is available for on-demand playback. Serve it through the Stream player embed URL:

```typescript
// src/player.ts — called from the feed Worker
export function streamPlayerUrl(recordingUid: string, accountId: string): string {
  return `https://iframe.videodelivery.net/${recordingUid}`;
}

export function streamThumbnailUrl(recordingUid: string, accountId: string): string {
  return `https://videodelivery.net/${recordingUid}/thumbnails/thumbnail.jpg?time=5s&height=200`;
}
```

The `videodelivery.net` domain is Cloudflare's CDN-backed stream delivery — no R2 egress cost, built-in adaptive bitrate.

## Anti-patterns
- Processing the webhook synchronously before returning a 204 — Cloudflare Stream retries on non-2xx responses; use `ctx.waitUntil()` to process after responding
- Skipping signature verification in staging environments — attackers can discover webhook URLs through CORS leaks and replay events
- Creating one Durable Object per live stream for notifications — a single global hub with per-stream subscription routing scales better than N stubs
- Storing the raw HLS manifest URL in D1 and serving it to clients — the token-scoped signed URL approach protects stream content from unauthorized sharing
- Not handling `live_input.disconnected` followed by `live_input.connected` within seconds — mobile network drops cause rapid reconnects; use an `ON CONFLICT DO UPDATE` pattern

## Gotchas
- Cloudflare Stream webhooks are delivered to exactly one endpoint; there is no fan-out — if you need multiple consumers, the receiving Worker must multiplex
- The `recording.ready` event fires with a delay of 30–120 seconds after stream end, not immediately — do not show the "replay available" UI until this event is received
- `recording.mode: "automatic"` starts recording as soon as the live input connects; there is no granular per-broadcast control unless you use the API to toggle modes
- Webhook retries use exponential backoff; if your Worker returns 500 repeatedly, you may miss events — implement idempotent handlers using `ON CONFLICT` upserts
- The `Webhook-Signature` header format changed in 2024; the `sig1=` prefix format described here is current as of 2026

## Verification
1. Deploy: `npx wrangler deploy`
2. Retrieve the webhook secret: `curl -X GET "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/stream/webhook" -H "Authorization: Bearer $CF_API_TOKEN"`
3. Use the Stream dashboard to test a live input connection (or use OBS/FFMPEG to push RTMP)
4. Check Worker logs: `npx wrangler tail --format=pretty`
5. Query D1: `SELECT * FROM live_posts ORDER BY started_at DESC LIMIT 5;`

## Related
- `cloudflare-stream-direct-creator-uploads.md`
- `stream-best-practices.md`
- `stream-adaptive-bitrate-mobile-hls-dash.md`
- `durable-objects-websocket-hibernation.md`
- `d1-best-practices.md`
- `browser-webcodecs-whip-streaming.md`

## Sources
- https://developers.cloudflare.com/stream/stream-live/
- https://developers.cloudflare.com/stream/manage-video/manage-live-streams/
- https://developers.cloudflare.com/stream/reference/security/securing-your-stream/
- https://developers.cloudflare.com/stream/stream-live/webhooks/
- https://developers.cloudflare.com/stream/viewing-videos/using-the-stream-player/
