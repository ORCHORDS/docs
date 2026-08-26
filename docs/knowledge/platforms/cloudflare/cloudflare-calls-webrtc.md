# cloudflare-calls-webrtc

**Issue:** Cloudflare Calls (SFU), WHIP/WHEP protocols, track/session REST API, vs Cloudflare Stream, pricing
**Date:** 2026-08-11
**Status:** documented

## Symptom
You want real-time audio/video in example.com. You don't know whether to
use Cloudflare Stream or Cloudflare Calls. You get a 400 from the Calls
REST API when creating a session. WHIP publishing fails with a 403.

## Root cause
**Cloudflare Calls is an SFU (Selective Forwarding Unit), not a CDN.**
It is designed for low-latency bidirectional real-time communication
(< 500 ms). Cloudflare Stream is for recorded/live-streamed video
delivered at CDN scale with higher latency (5–30 s).

**Source:** https://developers.cloudflare.com/calls/

## Cloudflare Calls vs Cloudflare Stream

| | Cloudflare Calls | Cloudflare Stream |
|---|---|---|
| Use case | Real-time WebRTC SFU | Live/on-demand video |
| Latency | < 500 ms | 5–30 s (HLS/DASH) |
| Protocol | WebRTC, WHIP, WHEP | RTMP, HLS, DASH |
| Participants | Many-to-many | One-to-many |
| Storage | No (ephemeral) | Yes (R2-backed) |
| Pricing | $0.05 / GB egress | $5 / 1000 min recorded |
| API surface | REST + WebRTC | REST + RTMP ingest |

**Use Calls** for: live collaboration, video chat, audio rooms,
real-time multiplayer.
**Use Stream** for: podcasts, webinar recordings, VOD, live streams to
thousands of viewers.

## Core concepts

- **App:** A Cloudflare Calls application, identified by `APP_ID`.
  Created once in the dashboard or via API.
- **Session:** Represents one peer connection. Each browser tab or
  device creates a session.
- **Track:** A single audio or video stream within a session. One
  session can have multiple tracks (e.g., camera + microphone).
- **WHIP** (WebRTC-HTTP Ingestion Protocol): publish a track via HTTP +
  SDP exchange.
- **WHEP** (WebRTC-HTTP Egress Protocol): subscribe to a track via HTTP
  + SDP exchange.

## Creating a session via REST API (from a Worker)

```typescript
const CF_CALLS_BASE = "https://rtc.live.cloudflare.com/v1/apps";

interface CallsSession {
  sessionId: string;
  sessionDescription: { type: string; sdp: string };
}

async function createSession(
  appId: string,
  apiToken: string,
): Promise<CallsSession> {
  const res = await fetch(`${CF_CALLS_BASE}/${appId}/sessions/new`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
  });
  if (!res.ok) throw new Error(`Calls API error: ${res.status} ${await res.text()}`);
  const data = await res.json<{ result: CallsSession }>();
  return data.result;
}
```

The `apiToken` is the **Calls API token** (not the global CF API token).
Generate it in the dashboard: Calls → (your app) → API Token.

## Publishing a track (WHIP from browser)

```typescript
// Browser-side: publish local camera
async function publishTrack(
  appId: string,
  sessionId: string,
  workerTokenEndpoint: string,
): Promise<void> {
  const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
  const pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.cloudflare.com:3478" }],
  });

  for (const track of stream.getTracks()) {
    pc.addTransceiver(track, { direction: "sendonly" });
  }

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  // Exchange SDP with Cloudflare Calls via your Worker (WHIP)
  const res = await fetch(`${workerTokenEndpoint}/calls/sessions/${sessionId}/tracks/new`, {
    method: "POST",
    headers: { "Content-Type": "application/sdp" },
    body: offer.sdp,
  });

  const answerSdp = await res.text();
  await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
}
```

Worker endpoint that proxies to Calls API:

```typescript
// Worker: POST /calls/sessions/:sessionId/tracks/new
async function handleTrackNew(
  request: Request,
  env: Env,
  sessionId: string,
): Promise<Response> {
  const offerSdp = await request.text();
  const res = await fetch(
    `${CF_CALLS_BASE}/${env.CALLS_APP_ID}/sessions/${sessionId}/tracks/new`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CALLS_API_TOKEN}`,
        "Content-Type": "application/sdp",
      },
      body: offerSdp,
    },
  );
  const answerSdp = await res.text();
  return new Response(answerSdp, {
    status: res.status,
    headers: { "Content-Type": "application/sdp" },
  });
}
```

## Subscribing to a remote track (WHEP from browser)

```typescript
async function subscribeTrack(
  sessionId: string,
  trackName: string,
  workerEndpoint: string,
): Promise<MediaStream> {
  const pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.cloudflare.com:3478" }],
  });

  const stream = new MediaStream();
  pc.ontrack = (event) => stream.addTrack(event.track);

  pc.addTransceiver("video", { direction: "recvonly" });
  pc.addTransceiver("audio", { direction: "recvonly" });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  // WHEP: exchange SDP via Worker
  const res = await fetch(
    `${workerEndpoint}/calls/sessions/${sessionId}/tracks/${encodeURIComponent(trackName)}`,
    {
      method: "GET",
      headers: {
        Accept: "application/sdp",
        "X-Offer-SDP": offer.sdp!,
      },
    },
  );

  const answerSdp = await res.text();
  await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
  return stream;
}
```

## Pricing model

Cloudflare Calls charges **$0.05 per GB of real-time media egress**.
Ingress (publishing) is free.

Estimate for a 1-hour video call with 4 participants:
- Each participant receives 3 streams (720p ≈ 1.5 Mbps each)
- Total egress: 4 × 3 × 1.5 Mbps × 3600 s = ~8.1 GB
- Cost: 8.1 × $0.05 = **~$0.40 per hour**

The first 1,000 participant-minutes per month are free.

```typescript
// Track your usage via Analytics Engine (optional)
async function logCallsUsage(env: Env, sessionId: string, bytesEgress: number) {
  env.ANALYTICS.writeDataPoint({
    blobs: [sessionId],
    doubles: [bytesEgress],
    indexes: ["calls_egress"],
  });
}
```

## wrangler.toml bindings

```toml
[vars]
CALLS_APP_ID = "your-app-id"  # not a secret

[secrets]
# wrangler secret put CALLS_API_TOKEN
```

## Verification
- Create a session via REST; verify `sessionId` in response
- Publish a track; verify ICE connection state reaches `connected`
- Subscribe from a second tab; verify video renders
- Check Calls dashboard for active session count

## Gotchas
- **The "API token scope" gotcha.** The Calls API token is app-scoped.
  Never use the global CF API token; it will 403 on the Calls endpoint.
- **The "ICE candidate" gotcha.** Cloudflare Calls uses Trickle ICE.
  Bundle all ICE candidates before sending the offer SDP (use
  `waitForIceGathering` or set `iceCandidatePoolSize = 0`).
- **The "session TTL" gotcha.** Sessions expire after 60 s of
  inactivity. Send a heartbeat or re-negotiate before the timeout.
- **The "WHIP vs fetch track" gotcha.** WHIP is the preferred publish
  path. The older `tracks/new` endpoint with JSON body still works but
  is not the recommended path for new integrations.
- **The "Stream vs Calls" gotcha.** Do not use Calls for recorded video
  delivery. Calls is ephemeral — no storage, no replay.

## Related
- `cloudflare/stream-best-practices.md`
- `cloudflare/realtime-sfu-best-practices.md`
- `cloudflare/durable-objects-patterns.md` (signalling server)
- CF Calls: https://developers.cloudflare.com/calls/
- CF Calls REST API: https://developers.cloudflare.com/calls/reference/rest-api/
- WHIP spec: https://www.ietf.org/archive/id/draft-ietf-wish-whip-01.txt
- WHEP spec: https://www.ietf.org/archive/id/draft-murillo-whep-02.txt
