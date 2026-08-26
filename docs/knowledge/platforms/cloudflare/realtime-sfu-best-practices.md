# realtime-sfu-best-practices

**Issue:** Realtime SFU — WebRTC video/audio at the edge
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a video call feature. You use WebRTC.
The SFU (Selective Forwarding Unit) is hard. You
manage regions. You scale WebRTC peers. You wish
it were a managed service.

## Root cause
**SFU is hard.** Use CF Realtime SFU.

**Source:** CF Realtime:
https://developers.cloudflare.com/realtime/sfu/

## The "Realtime SFU" concept

CF Realtime SFU is serverless WebRTC:
- **Selective Forwarding Unit:** Media routing
- **WebRTC CDN:** Fanout delivery
- **Global:** 100s of cities
- **Serverless:** No infra
- **No region:** Auto

The SFU is at the edge.

## The "use cases" pattern

For use cases:
- **Video call:** 1:1 or group
- **Live broadcast:** 1:N (creator → many)
- **Interactive stream:** Low-latency
- **Audio room:** Voice-only
- **Data channel:** Beyond video

The use case is yours.

## The "create session" pattern

For a session:
```ts
const session = await fetch('https://api.realtime.cloudflare.com/v1/apps/{appId}/sessions/new', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${env.REALTIME_API_KEY}` },
  body: JSON.stringify({
    sessionId: 'unique-id',
  }),
});
```

The session is created.

## The "join" pattern

For a client to join:
```ts
const response = await fetch('https://api.realtime.cloudflare.com/v1/apps/{appId}/sessions/{sessionId}/connections/new', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${env.REALTIME_API_KEY}` },
  body: JSON.stringify({
    userId: 'u_123',
  }),
});

const { sessionDescription } = await response.json();
// Send to the client for WebRTC negotiation
```

The client joins.

## The "WebRTC client" pattern

For the client:
```ts
const pc = new RTCPeerConnection();

// Use the sessionDescription from the server
await pc.setRemoteDescription(sessionDescription);

// Add local media
const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
stream.getTracks().forEach(track => pc.addTrack(track, stream));

// Send ICE candidates
pc.addEventListener('icecandidate', (event) => {
  if (event.candidate) {
    sendIceCandidate(event.candidate);
  }
});
```

The client is connected.

## The "WebSocket adapter" pattern

For streaming to a WebSocket:
```ts
const response = await fetch('https://api.realtime.cloudflare.com/v1/apps/{appId}/adapters/websocket/new', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${env.REALTIME_API_KEY}` },
  body: JSON.stringify({
    sessionId: 'session-id',
    trackId: 'video-track',
    url: 'wss://my-endpoint.com/process',
  }),
});
```

The audio/video streams to a WebSocket.

**New 2026:** The adapter now auto-reconnects and buffers
during brief disconnects (5 second window).

## The "audio format" pattern

For audio (WebSocket):
- **Sample rate:** 48 kHz
- **Channels:** Stereo
- **Format:** PCM

The audio is in PCM.

## The "video format" pattern

For video (WebSocket):
- **Format:** JPEG
- **Frame rate:** ~1 FPS (beta, not configurable)
- **Use:** Recordings, snapshots

The video is in JPEG.

## The "supported codecs" pattern

For codecs:
- **Input:** H.264, H.265, VP8, VP9
- **WebRTC:** Standard
- **WebSocket:** JPEG only

The codecs are standard.

## The "Realtime SFU limits" pattern

For limits:
- **Sessions:** Per app
- **Participants:** Per session
- **Bandwidth:** Per session
- **Duration:** No limit
- **Region:** Auto

The limits are checked.

## The "Realtime SFU vs alternatives" choice

| Use case | Use |
|---|---|
| **Video call (small group)** | Realtime SFU |
| **Broadcast (1:N)** | Realtime SFU |
| **Twitch-scale** | Stream Live |
| **Self-host** | Janus, mediasoup |

For most apps, **Realtime SFU** is the right answer.

## The "Realtime SFU anti-pattern" anti-patterns

### 1. Mesh WebRTC
- **Issue:** N^2 connections
- **Fix:** SFU

### 2. No SFU
- **Issue:** Can't scale
- **Fix:** Realtime SFU

### 3. No recording
- **Issue:** Lost calls
- **Fix:** Stream Live + recording

### 4. No monitoring
- **Issue:** Don't know quality
- **Fix:** Realtime dashboard

## Verification
- **Test:** Session creates
- **Test:** Client joins
- **Test:** Media flows
- **Live:** Quality monitored
- **Audit:** Quarterly review

## Gotchas
- **The "mesh WebRTC" anti-pattern.** Use SFU.
- **The "no recording" anti-pattern.** Record.

## Related
- `cloudflare/browser-run-best-practices.md`
- `cloudflare/durable-objects-best-practices.md`
- `feature-cookbook-realtime.md`
- CF Realtime: https://developers.cloudflare.com/realtime/sfu/
- WebRTC: https://webrtc.org/
