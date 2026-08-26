# WebTransport + Cloudflare Workers Real-Time Streaming

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need sub-100 ms bidirectional data channels for live feeds, collaborative cursors, or
multiplayer features on example project WebSockets work but carry HTTP/1.1 head-of-line blocking
over TCP. WebRTC is peer-to-peer and requires a signalling server. WebTransport over HTTP/3
(QUIC) gives you ordered/unordered datagrams and reliable streams without those constraints,
routed through Cloudflare's anycast edge.

## Context

WebTransport is a browser API that opens a multiplexed QUIC session to an HTTP/3 server.
Cloudflare Workers support WebTransport via the `WebSocketPair` analogy — the
`cf-workers-webtransport` approach uses Durable Objects to manage session state. As of 2026,
Workers expose `WebTransport` through the `request.upgrade("webtransport")` path inside a
Durable Object or via the `acceptWebTransport()` method. The client uses `new WebTransport(url)`.
QUIC requires a TLS certificate; Cloudflare terminates TLS at the edge automatically.

## Server: Durable Object WebTransport Handler

```typescript
// src/transport-room.ts
export class TransportRoom implements DurableObject {
  private sessions = new Map<string, WebTransport>();

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("upgrade") !== "webtransport") {
      return new Response("Expected WebTransport upgrade", { status: 426 });
    }

    const { session, response } = request.acceptWebTransport();
    const id = crypto.randomUUID();
    this.sessions.set(id, session);

    this.handleSession(id, session).catch(console.error);
    return response;
  }

  private async handleSession(id: string, session: WebTransport): Promise<void> {
    try {
      // Accept incoming unidirectional streams from the client
      const reader = session.incomingUnidirectionalStreams.getReader();
      while (true) {
        const { value: stream, done } = await reader.read();
        if (done) break;
        this.pipeToOthers(id, stream).catch(() => {});
      }
    } finally {
      this.sessions.delete(id);
    }
  }

  private async pipeToOthers(senderId: string, stream: ReadableStream): Promise<void> {
    const chunks: Uint8Array[] = [];
    const reader = stream.getReader();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    const payload = mergeChunks(chunks);

    for (const [id, session] of this.sessions) {
      if (id === senderId) continue;
      const writer = await session.createUnidirectionalStream();
      const w = writer.getWriter();
      await w.write(payload);
      await w.close();
    }
  }
}

function mergeChunks(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.byteLength, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) { out.set(c, offset); offset += c.byteLength; }
  return out;
}
```

## Worker Entry Point

```typescript
// src/index.ts
import { TransportRoom } from "./transport-room";
export { TransportRoom };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/wt/")) {
      const roomId = url.pathname.slice(4) || "default";
      const id = env.TRANSPORT_ROOM.idFromName(roomId);
      const stub = env.TRANSPORT_ROOM.get(id);
      return stub.fetch(request);
    }
    return new Response("Not found", { status: 404 });
  },
};

interface Env {
  TRANSPORT_ROOM: DurableObjectNamespace;
}
```

## Client: Opening a WebTransport Session

```typescript
// src/client/transport.ts
export async function openTransport(roomId: string) {
  const url = `https://example.com/wt/${encodeURIComponent(roomId)}`;
  const transport = new WebTransport(url);

  await transport.ready;
  console.log("WebTransport ready");

  transport.closed.then(() => console.log("Transport closed"));

  return {
    async send(data: Uint8Array): Promise<void> {
      const stream = await transport.createUnidirectionalStream();
      const writer = stream.getWriter();
      await writer.write(data);
      await writer.close();
    },
    async receiveLoop(onMessage: (data: Uint8Array) => void): Promise<void> {
      const reader = transport.incomingUnidirectionalStreams.getReader();
      while (true) {
        const { value: stream, done } = await reader.read();
        if (done) break;
        const chunks: Uint8Array[] = [];
        const sr = stream.getReader();
        while (true) {
          const { value, done: d } = await sr.read();
          if (d) break;
          chunks.push(value);
        }
        onMessage(mergeChunks(chunks));
      }
    },
    close() { transport.close(); },
  };
}
```

## Datagrams for Fire-and-Forget Events

```typescript
// Unreliable but ultra-low-latency — good for cursor positions, heartbeats
async function sendDatagram(transport: WebTransport, payload: Uint8Array) {
  const writer = transport.datagrams.writable.getWriter();
  await writer.write(payload);
  writer.releaseLock();
}

async function receivDatagramLoop(
  transport: WebTransport,
  onDatagram: (data: DatagramEvent) => void
) {
  const reader = transport.datagrams.readable.getReader();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    onDatagram({ data: value, timestamp: Date.now() });
  }
}
```

## React Hook Integration

```typescript
// src/hooks/useWebTransport.ts
import { useEffect, useRef } from "react";
import { openTransport } from "../client/transport";

export function useWebTransport(
  roomId: string,
  onMessage: (data: Uint8Array) => void
) {
  const ref = useRef<Awaited<ReturnType<typeof openTransport>> | null>(null);

  useEffect(() => {
    let cancelled = false;
    openTransport(roomId).then((t) => {
      if (cancelled) { t.close(); return; }
      ref.current = t;
      t.receiveLoop(onMessage).catch(() => {});
    });
    return () => {
      cancelled = true;
      ref.current?.close();
      ref.current = null;
    };
  }, [roomId]);

  return (data: Uint8Array) => ref.current?.send(data);
}
```

## Anti-patterns

- **Using WebTransport for all traffic** — HTTP/3 is good for latency-sensitive fan-out; use
  regular fetch for REST calls.
- **Opening one session per message** — `new WebTransport()` is expensive; keep one session
  alive and multiplex streams.
- **Ignoring `transport.closed`** — QUIC connections drop silently; always handle the
  `closed` promise and reconnect.
- **Sending JSON as text** — WebTransport carries binary; encode with `TextEncoder` or
  MessagePack.

## Gotchas

- Cloudflare Workers WebTransport support requires `compatibility_date = "2024-09-23"` or
  later and the `experimental:webtransport` compat flag in `wrangler.toml`.
- Datagrams have a maximum size equal to the QUIC path MTU (~1200 bytes). Larger payloads
  must use streams.
- Chrome requires the server to present a valid TLS cert; Cloudflare handles this but
  `localhost` dev needs a self-signed cert registered via DevTools `--ignore-certificate-errors-spki-list`.
- Safari support landed in Safari 18 (2024); check `"WebTransport" in globalThis` before use.

## Verification

```bash
# Check Workers compat flags support
npx wrangler versions view

# Browser test — open DevTools console on example.com
const t = new WebTransport("https://example.com/wt/test");
await t.ready;
console.log("connected");
```

## Related

- `websocket-durable-objects-realtime-ui.md`
- `webrtc-signaling-durable-objects-edge.md`
- `server-sent-events-streaming-ui.md`
- `broadcastchannel-cross-tab-coordination.md`

## Sources

- https://developer.chrome.com/docs/capabilities/web-apis/webtransport
- https://developers.cloudflare.com/workers/runtime-apis/webtransport/
- https://w3c.github.io/webtransport/
- https://developers.cloudflare.com/durable-objects/
