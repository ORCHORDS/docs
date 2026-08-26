# Cloudflare Calls WebRTC Signaling with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to build a real-time video or audio call feature into your application without provisioning a TURN/STUN server cluster or managing WebRTC media infrastructure. Cloudflare Calls provides managed media routing globally, but you still need a signaling layer — the channel through which peers exchange SDP offers, answers, and ICE candidates — and this signaling server must be low-latency and globally distributed. You want both the signaling and the media handled within the Cloudflare ecosystem.

## Context

Cloudflare Calls is a serverless WebRTC media plane: you create a session via the REST API, exchange SDP with the Calls service (not directly peer-to-peer), and Calls handles media relay and TURN. The signaling path (SDP offer/answer + ICE candidates) is not provided by Cloudflare Calls itself — you build it as a Worker endpoint. Durable Objects are the natural fit for the signaling channel because they provide a persistent WebSocket hub co-located with Cloudflare's network. The `@cloudflare/calls-sdk` client-side package wraps the session and track management API, reducing boilerplate in the browser.

## Creating a Session via the Calls REST API

```typescript
// src/signaling-worker.ts  (excerpt)
// POST /session/new  — called by the browser before getUserMedia

const CALLS_APP_ID = "<your-calls-app-id>";
const CALLS_SECRET = "<your-calls-app-secret>"; // wrangler secret put CALLS_SECRET

async function createCallsSession(): Promise<{ sessionId: string }> {
  const res = await fetch(
    `https://rtc.live.cloudflare.com/v1/apps/${CALLS_APP_ID}/sessions/new`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${CALLS_SECRET}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    }
  );

  if (!res.ok) {
    throw new Error(`Calls session creation failed: ${res.status}`);
  }

  const data = (await res.json()) as { sessionId: string };
  return data;
}
```

## Exchanging SDP Offer / Answer via a Workers Endpoint

```typescript
// src/signaling-worker.ts
export interface Env {
  ROOM: DurableObjectNamespace;  // ICE candidate relay
  CALLS_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/session/new") {
      const session = await createCallsSession();
      return Response.json(session);
    }

    if (request.method === "POST" && url.pathname === "/session/offer") {
      // Browser sends its SDP offer; we forward to Calls and return the answer
      const { sessionId, offer } = (await request.json()) as {
        sessionId: string;
        offer: RTCSessionDescriptionInit;
      };

      const answerRes = await fetch(
        `https://rtc.live.cloudflare.com/v1/apps/${CALLS_APP_ID}/sessions/${sessionId}/tracks/new`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.CALLS_SECRET}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            sessionDescription: { type: "offer", sdp: offer.sdp },
            tracks: [{ location: "local", mid: "0", trackName: "video" }],
          }),
        }
      );

      const answer = await answerRes.json();
      return Response.json(answer);
    }

    // WebSocket upgrade for ICE candidates — routed to Durable Object
    if (request.headers.get("Upgrade") === "websocket") {
      const roomId = url.searchParams.get("room") ?? "default";
      const roomStub = env.ROOM.get(env.ROOM.idFromName(roomId));
      return roomStub.fetch(request);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## Durable Object WebSocket Channel for ICE Candidates

```typescript
// src/room-do.ts
export class Room {
  private sessions: Set<WebSocket> = new Set();
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    this.state.acceptWebSocket(server);
    this.sessions.add(server);

    server.addEventListener("message", (event) => {
      // Broadcast ICE candidate to all other peers in the room
      for (const ws of this.sessions) {
        if (ws !== server && ws.readyState === WebSocket.OPEN) {
          ws.send(event.data);
        }
      }
    });

    server.addEventListener("close", () => {
      this.sessions.delete(server);
    });

    return new Response(null, { status: 101, webSocket: client });
  }
}
```

## TURN Credential Generation via the Calls API

```typescript
// Generate ephemeral TURN credentials for a session
async function getTurnCredentials(sessionId: string, callsSecret: string) {
  const res = await fetch(
    `https://rtc.live.cloudflare.com/v1/apps/${CALLS_APP_ID}/sessions/${sessionId}/turn`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${callsSecret}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ttl: 86400 }), // 24-hour credentials
    }
  );

  const creds = (await res.json()) as {
    username: string;
    credential: string;
    urls: string[];
  };

  return creds;
}
// Pass creds.username, creds.credential, and creds.urls to the
// browser RTCPeerConnection iceServers config.
```

## Minimal Browser Video Call Using @cloudflare/calls-sdk

```typescript
// browser/main.ts
import { CallsSession } from "@cloudflare/calls-sdk";

async function startCall() {
  const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });

  // 1. Create Calls session via your Worker endpoint
  const { sessionId } = await fetch("/session/new", { method: "POST" }).then((r) => r.json());

  // 2. Get TURN credentials
  const turnCreds = await fetch(`/session/${sessionId}/turn`, { method: "POST" })
    .then((r) => r.json());

  // 3. Connect Calls SDK session
  const session = new CallsSession({
    appId: "<your-calls-app-id>",
    sessionId,
    iceServers: [{ urls: turnCreds.urls, username: turnCreds.username, credential: turnCreds.credential }],
  });

  // 4. Push local tracks
  for (const track of stream.getTracks()) {
    await session.pushTrack(track);
  }

  // 5. Open WebSocket for ICE candidate signaling
  const ws = new WebSocket(`wss://your-worker.example.com/?room=call-${sessionId}`);

  session.onIceCandidate = (candidate) => {
    ws.send(JSON.stringify({ type: "ice", candidate }));
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "ice") session.addIceCandidate(msg.candidate);
  };

  document.getElementById("local-video").srcObject = stream;
}
```

## Anti-patterns

- **Storing TURN credentials long-term** — TURN credentials are single-use tokens tied to a session; request them per-call with a short TTL and never cache them across sessions.
- **Broadcasting SDP over the Durable Object WebSocket** — the Durable Object should relay ICE candidates only; SDP exchange must happen via the Calls REST API, not peer-to-peer through your WebSocket.
- **Skipping the Calls API for media relay and doing direct peer-to-peer** — direct P2P bypasses Cloudflare's global media network and TURN, causing connectivity failures behind symmetric NATs.

## Gotchas

- The Calls API base URL is `https://rtc.live.cloudflare.com` — different from the standard `api.cloudflare.com` base used by other services.
- `@cloudflare/calls-sdk` is a browser-only package; do not import it in a Worker script.
- Durable Objects used for WebSocket signaling must enable Hibernation (`ctx.acceptWebSocket()`) for rooms that stay idle between messages, otherwise the DO is billed for idle CPU time.
- The Calls App ID and Secret are separate credentials created in the Cloudflare dashboard under **Calls** — they are not the same as your account API token.
- Each Calls session supports up to 100 simultaneous tracks; for larger conferences, use Calls' SFU mode with a server-side forwarding topology.

## Verification

```bash
# Create a test Calls session manually
curl -X POST \
  "https://rtc.live.cloudflare.com/v1/apps/$CALLS_APP_ID/sessions/new" \
  -H "Authorization: Bearer $CALLS_SECRET" | jq .

# Deploy the signaling worker
wrangler deploy

# Test WebSocket signaling endpoint
npx wscat -c wss://signaling-worker.example.workers.dev/?room=test

# Check Durable Object class is bound correctly
wrangler tail signaling-worker --format pretty
```

## Related

- `workers-for-platforms-tenant-custom-domains.md`
- `workers-tcp-socket-database-proxy.md`

## Sources

- Cloudflare Calls documentation — https://developers.cloudflare.com/calls/
- Calls REST API reference — https://developers.cloudflare.com/calls/reference/rest-api/
- @cloudflare/calls-sdk npm — https://www.npmjs.com/package/@cloudflare/calls-sdk
- Durable Objects WebSocket hibernation — https://developers.cloudflare.com/durable-objects/best-practices/websockets/
