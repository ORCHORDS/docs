# WebRTC Signaling Server with Cloudflare Durable Objects

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You need a low-latency WebRTC signaling server — exchanging SDP offers/answers and ICE candidates between peers — without a persistent origin server. Cloudflare Durable Objects provide a single, globally-consistent JavaScript instance per "room" with a built-in WebSocket hibernation API, making them the ideal edge primitive for WebRTC signaling: the Durable Object lives as close to your users as Cloudflare's network allows, and idle WebSocket connections are hibernated at zero cost.

---

## Context

WebRTC establishes peer-to-peer audio/video/data streams directly between browsers, but requires a signaling channel to exchange:
1. **SDP** (Session Description Protocol) — describes media capabilities
2. **ICE candidates** — network addresses for NAT traversal

Both must transit a server before the direct connection is established. Durable Objects are perfect because:
- Each room is a single DO instance — no race conditions or shared-state bugs
- The WebSocket Hibernation API keeps connections open without consuming CPU while idle
- TURN server integration (Cloudflare Calls or third-party) handles symmetric NAT

---

## Durable Object: Room Signaling Hub

```typescript
// src/Room.ts

export interface RoomMessage {
  type: "offer" | "answer" | "ice-candidate" | "join" | "leave";
  from: string;
  to?: string;   // undefined = broadcast
  payload: unknown;
}

export class Room implements DurableObject {
  private sessions = new Map<string, WebSocket>();
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
    // Restore hibernated sessions on wake
    for (const ws of state.getWebSockets()) {
      const meta = ws.deserializeAttachment() as { peerId: string };
      if (meta?.peerId) this.sessions.set(meta.peerId, ws);
    }
  }

  async fetch(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get("Upgrade");
    if (upgradeHeader !== "websocket") {
      return new Response("Expected WebSocket upgrade", { status: 426 });
    }

    const url = new URL(request.url);
    const peerId = url.searchParams.get("peerId") ?? crypto.randomUUID();

    const { 0: client, 1: server } = new WebSocketPair();
    this.state.acceptWebSocket(server);
    server.serializeAttachment({ peerId });
    this.sessions.set(peerId, server);

    // Notify existing peers of the new joiner
    this.broadcast(
      { type: "join", from: peerId, payload: { peerId } },
      peerId
    );

    return new Response(null, {
      status: 101,
      webSocket: client,
    });
  }

  // Called by Workers runtime on WebSocket message (hibernation-compatible)
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer) {
    const { peerId } = ws.deserializeAttachment() as { peerId: string };
    const msg: RoomMessage = JSON.parse(
      typeof message === "string" ? message : new TextDecoder().decode(message)
    );
    msg.from = peerId;

    if (msg.to) {
      // Unicast: send to one peer
      const target = this.sessions.get(msg.to);
      if (target) {
        target.send(JSON.stringify(msg));
      }
    } else {
      // Broadcast: relay to all other peers
      this.broadcast(msg, peerId);
    }
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string) {
    const { peerId } = ws.deserializeAttachment() as { peerId: string };
    this.sessions.delete(peerId);
    this.broadcast({ type: "leave", from: peerId, payload: {} }, peerId);
  }

  async webSocketError(ws: WebSocket, error: unknown) {
    const { peerId } = ws.deserializeAttachment() as { peerId: string };
    this.sessions.delete(peerId);
  }

  private broadcast(msg: RoomMessage, excludePeerId?: string) {
    const text = JSON.stringify(msg);
    for (const [id, ws] of this.sessions) {
      if (id !== excludePeerId) {
        try {
          ws.send(text);
        } catch {
          this.sessions.delete(id);
        }
      }
    }
  }
}
```

---

## Worker Entry Point

```typescript
// src/index.ts

import { Room } from "./Room";

export { Room };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/room/")) {
      const roomId = url.pathname.split("/room/")[1].split("/")[0];
      if (!roomId) {
        return new Response("Room ID required", { status: 400 });
      }

      const id = env.ROOM.idFromName(roomId);
      const stub = env.ROOM.get(id);
      return stub.fetch(request);
    }

    return new Response("Not Found", { status: 404 });
  },
};

interface Env {
  ROOM: DurableObjectNamespace;
}
```

`wrangler.toml`:

```toml
name = "webrtc-signaling"
compatibility_date = "2024-09-23"

[[durable_objects.bindings]]
name = "ROOM"
class_name = "Room"

[[migrations]]
tag = "v1"
new_classes = ["Room"]
```

---

## Browser Client: SDP Exchange

```typescript
// client/signaling.ts

export class SignalingClient extends EventTarget {
  private ws: WebSocket;
  readonly peerId: string;

  constructor(roomId: string, peerId?: string) {
    super();
    this.peerId = peerId ?? crypto.randomUUID();
    const url = new URL(`wss://signaling.example.com/room/${roomId}`);
    url.searchParams.set("peerId", this.peerId);
    this.ws = new WebSocket(url.toString());

    this.ws.addEventListener("message", (e) => {
      const msg = JSON.parse(e.data as string);
      this.dispatchEvent(new CustomEvent(msg.type, { detail: msg }));
    });
  }

  send(type: string, to: string | undefined, payload: unknown) {
    this.ws.send(JSON.stringify({ type, to, payload }));
  }

  close() {
    this.ws.close();
  }
}

// Usage
const signaling = new SignalingClient("my-room-id");
const pc = new RTCPeerConnection({
  iceServers: [{ urls: "stun:stun.cloudflare.com:3478" }],
});

// Send ICE candidates through the signaling server
pc.addEventListener("icecandidate", ({ candidate }) => {
  if (candidate) {
    signaling.send("ice-candidate", remotePeerId, candidate.toJSON());
  }
});

// Handle incoming messages
signaling.addEventListener("offer", async (e: Event) => {
  const { from, payload } = (e as CustomEvent).detail;
  await pc.setRemoteDescription(new RTCSessionDescription(payload));
  const answer = await pc.createAnswer();
  await pc.setLocalDescription(answer);
  signaling.send("answer", from, answer);
});

signaling.addEventListener("ice-candidate", async (e: Event) => {
  const { payload } = (e as CustomEvent).detail;
  await pc.addIceCandidate(new RTCIceCandidate(payload));
});
```

---

## Initiating a Call

```typescript
// client/call.ts

import { SignalingClient } from "./signaling";

export async function initiateCall(
  roomId: string,
  remotePeerId: string,
  stream: MediaStream
): Promise<RTCPeerConnection> {
  const signaling = new SignalingClient(roomId);
  const pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.cloudflare.com:3478" }],
  });

  stream.getTracks().forEach((track) => pc.addTrack(track, stream));

  pc.addEventListener("icecandidate", ({ candidate }) => {
    if (candidate) {
      signaling.send("ice-candidate", remotePeerId, candidate.toJSON());
    }
  });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  signaling.send("offer", remotePeerId, offer);

  signaling.addEventListener("answer", async (e: Event) => {
    const { payload } = (e as CustomEvent).detail;
    await pc.setRemoteDescription(new RTCSessionDescription(payload));
  });

  signaling.addEventListener("ice-candidate", async (e: Event) => {
    const { payload } = (e as CustomEvent).detail;
    await pc.addIceCandidate(new RTCIceCandidate(payload));
  });

  return pc;
}
```

---

## Anti-patterns

- **One Durable Object per user instead of per room**: Creates an unnecessary fan-out pattern where every peer must send messages to every other peer's DO. One DO per room centralises signaling.
- **Not using WebSocket Hibernation**: Holding WebSocket connections open with `new WebSocketPair()` in a standard Worker (not DO) burns CPU-time for idle connections. Always use `state.acceptWebSocket()` in a Durable Object for hibernation.
- **Passing media through the signaling server**: SDP and ICE candidates are small (<1 KB). Never relay the actual audio/video stream through the DO — that defeats WebRTC's purpose and will exhaust bandwidth limits.
- **Hardcoding STUN only**: STUN cannot traverse symmetric NAT. Integrate a TURN server (Cloudflare Calls, Twilio, or Metered.ca) for production deployments.
- **No room expiry or peer cleanup**: DO instances persist until explicitly deleted. Call `this.state.storage.deleteAll()` and `this.state.abort()` when a room is empty for a configurable TTL.

---

## Gotchas

- Durable Object WebSocket Hibernation requires `compatibility_date = "2023-08-01"` or newer. Without it, `state.acceptWebSocket()` is not available.
- `ws.deserializeAttachment()` returns `null` if no attachment was set — always guard against null before destructuring.
- The DO `webSocketClose` handler fires with code 1006 (abnormal closure) when the client disconnects without a clean close frame (e.g. tab killed). Handle this identically to a clean close.
- `env.ROOM.idFromName(roomId)` produces a deterministic ID from the string. Two Workers calling `idFromName("same-string")` always route to the same DO instance globally — no coordination needed.
- WebSocket messages larger than 1 MB will be rejected by the Workers runtime. Chunk large payloads (e.g. SDP + ICE batches) if needed.

---

## Verification

```bash
# Local testing with wrangler
wrangler dev --local

# Open two browser tabs pointing at the same room
# Tab 1: const sc = new SignalingClient("test-room", "peer-a");
# Tab 2: const sc = new SignalingClient("test-room", "peer-b");
# Verify "join" events fire in each tab when the other connects

# Check DO instance count
wrangler durable-objects list --local
```

---

## Related

- `websocket-durable-objects-realtime-ui.md` — general DO WebSocket patterns for chat/presence
- `websocket-realtime-ui-patterns.md` — client-side WebSocket reconnect and state management
- `server-sent-events-streaming-ui.md` — unidirectional alternative for non-WebRTC streaming
- `web-locks-cross-context-coordination.md` — coordinating multiple tabs on the client side

---

## Sources

- Cloudflare Durable Objects WebSocket Hibernation API: https://developers.cloudflare.com/durable-objects/api/websockets/
- WebRTC API — MDN: https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API
- RTCPeerConnection — MDN: https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection
- Cloudflare Calls (TURN): https://developers.cloudflare.com/calls/
