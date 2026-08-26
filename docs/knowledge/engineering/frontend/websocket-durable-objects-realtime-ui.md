# WebSocket Real-Time UI with Cloudflare Durable Objects

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You need multiple browser clients to see the same live state—a collaborative document, a live auction bid, a multiplayer cursor overlay, a shared music queue. Stateless Workers cannot hold a WebSocket connection because they are terminated after each request. A traditional Node.js WebSocket server is another origin to deploy and scale. Durable Objects solve this by providing a single, location-pinned JavaScript instance that can hold thousands of persistent WebSocket connections simultaneously, with Hibernation API support so idle connections cost nothing.

---

## Context

Cloudflare Durable Objects give you a named, strongly-consistent actor—one JavaScript class instance—that owns a private SQLite-backed storage and can maintain WebSocket connections using the **WebSocket Hibernation API**. The pattern:

1. A client connects to a Cloudflare Worker via `wss://`.
2. The Worker routes the upgrade to a Durable Object by name (e.g., room ID).
3. The Durable Object accepts the WebSocket via `this.ctx.acceptWebSocket(ws)` and registers it with the runtime so the DO can hibernate between messages while keeping all connections alive.
4. When any client sends a message, the DO's `webSocketMessage` handler broadcasts to all other registered sockets.
5. The React UI wraps the WebSocket in a hook, managing reconnect logic and React state synchronisation.

---

## 1. Durable Object Class

```typescript
// src/room.ts
import { DurableObject } from 'cloudflare:workers';

interface RoomMessage {
  type: 'cursor' | 'chat' | 'state';
  payload: unknown;
  userId: string;
  ts: number;
}

export class Room extends DurableObject {
  // No constructor override needed; ctx and env are injected by the runtime.

  async fetch(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get('Upgrade');
    if (upgradeHeader !== 'websocket') {
      return new Response('Expected WebSocket upgrade', { status: 426 });
    }

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    // Hibernation API: runtime manages the socket lifecycle
    this.ctx.acceptWebSocket(server, [this.getRoomId(request)]);

    // Persist join event to Durable Object storage
    const count = ((await this.ctx.storage.get<number>('connectionCount')) ?? 0) + 1;
    await this.ctx.storage.put('connectionCount', count);

    return new Response(null, { status: 101, webSocket: client });
  }

  // Called by the runtime when a message arrives on any hibernating socket
  webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
    let parsed: RoomMessage;
    try {
      parsed = JSON.parse(typeof message === 'string' ? message : new TextDecoder().decode(message));
    } catch {
      ws.send(JSON.stringify({ type: 'error', message: 'Invalid JSON' }));
      return;
    }

    // Broadcast to all sockets in this room except the sender
    const roomTag = ws.deserializeAttachment() as string | undefined;
    for (const peer of this.ctx.getWebSockets()) {
      if (peer !== ws && peer.readyState === WebSocket.OPEN) {
        peer.send(JSON.stringify(parsed));
      }
    }
  }

  webSocketClose(ws: WebSocket, code: number, reason: string): void {
    ws.close(code, reason);
  }

  webSocketError(ws: WebSocket, error: unknown): void {
    console.error('WebSocket error in room', error);
    ws.close(1011, 'Internal error');
  }

  private getRoomId(request: Request): string {
    return new URL(request.url).searchParams.get('roomId') ?? 'default';
  }
}
```

---

## 2. Worker Entrypoint: Routing Upgrades

```typescript
// src/index.ts
import { Room } from './room';

export { Room };

interface Env {
  ROOM: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/ws') {
      const roomId = url.searchParams.get('roomId') ?? 'default';
      // Each unique roomId is a distinct DO instance
      const id = env.ROOM.idFromName(roomId);
      const stub = env.ROOM.get(id);
      return stub.fetch(request);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

```toml
# wrangler.toml
name = "realtime-rooms"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[durable_objects.bindings]]
name = "ROOM"
class_name = "Room"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["Room"]
```

---

## 3. React WebSocket Hook

```typescript
// hooks/useRoomSocket.ts
import { useEffect, useRef, useCallback, useState } from 'react';

type MessageHandler = (msg: unknown) => void;

interface UseRoomSocketOptions {
  roomId: string;
  onMessage: MessageHandler;
  onOpen?: () => void;
  onClose?: () => void;
}

export function useRoomSocket({ roomId, onMessage, onOpen, onClose }: UseRoomSocketOptions) {
  const ws = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(1000);
  const unmounted = useRef(false);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (unmounted.current) return;

    const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws?roomId=${encodeURIComponent(roomId)}`;
    const socket = new WebSocket(wsUrl);
    ws.current = socket;

    socket.addEventListener('open', () => {
      reconnectDelay.current = 1000; // reset backoff on successful connection
      setConnected(true);
      onOpen?.();
    });

    socket.addEventListener('message', (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch {
        // malformed message; ignore
      }
    });

    socket.addEventListener('close', () => {
      setConnected(false);
      onClose?.();
      if (!unmounted.current) {
        // exponential backoff, cap at 30 s
        setTimeout(connect, Math.min(reconnectDelay.current, 30_000));
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30_000);
      }
    });

    socket.addEventListener('error', () => {
      socket.close(); // triggers the close handler and reconnect
    });
  }, [roomId, onMessage, onOpen, onClose]);

  useEffect(() => {
    unmounted.current = false;
    connect();
    return () => {
      unmounted.current = true;
      ws.current?.close(1000, 'Component unmounted');
    };
  }, [connect]);

  const send = useCallback((payload: unknown) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    }
  }, []);

  return { send, connected };
}
```

---

## 4. Collaborative Cursor Component

```tsx
// components/CursorOverlay.tsx
import { useState, useCallback, useEffect } from 'react';
import { useRoomSocket } from '../hooks/useRoomSocket';

interface CursorPosition {
  userId: string;
  x: number;
  y: number;
  color: string;
}

interface CursorMessage {
  type: 'cursor';
  payload: CursorPosition;
  userId: string;
  ts: number;
}

const MY_USER_ID = crypto.randomUUID(); // stable per-session
const MY_COLOR = `hsl(${Math.random() * 360}, 70%, 50%)`;

export function CursorOverlay({ roomId }: { roomId: string }) {
  const [cursors, setCursors] = useState<Map<string, CursorPosition>>(new Map());

  const onMessage = useCallback((msg: unknown) => {
    const m = msg as CursorMessage;
    if (m.type === 'cursor') {
      setCursors((prev) => new Map(prev).set(m.userId, m.payload));
    }
  }, []);

  const { send, connected } = useRoomSocket({ roomId, onMessage });

  useEffect(() => {
    const handleMouseMove = throttle((e: MouseEvent) => {
      const position: CursorPosition = {
        userId: MY_USER_ID,
        x: e.clientX / window.innerWidth,  // normalised 0–1
        y: e.clientY / window.innerHeight,
        color: MY_COLOR,
      };
      send({ type: 'cursor', payload: position, userId: MY_USER_ID, ts: Date.now() });
    }, 50); // 20 fps max

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [send]);

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-50">
      {!connected && (
        <div className="absolute top-2 right-2 text-xs text-amber-500">Reconnecting…</div>
      )}
      {[...cursors.values()].map((cursor) => (
        <div
          key={cursor.userId}
          className="absolute w-3 h-3 rounded-full -translate-x-1/2 -translate-y-1/2 transition-transform duration-50"
          style={{
            left: `${cursor.x * 100}%`,
            top: `${cursor.y * 100}%`,
            backgroundColor: cursor.color,
          }}
        />
      ))}
    </div>
  );
}

function throttle<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let last = 0;
  return ((...args) => {
    const now = Date.now();
    if (now - last >= ms) { last = now; fn(...args); }
  }) as T;
}
```

---

## 5. Durable Object Storage for Persistent Room State

```typescript
// src/room.ts (extended)
interface RoomState {
  messages: Array<{ userId: string; text: string; ts: number }>;
}

// Inside Room class:
async getState(): Promise<RoomState> {
  return (await this.ctx.storage.get<RoomState>('state')) ?? { messages: [] };
}

async appendMessage(msg: { userId: string; text: string; ts: number }): Promise<void> {
  const state = await this.getState();
  state.messages = [...state.messages.slice(-99), msg]; // keep last 100
  await this.ctx.storage.put('state', state);
}

// In webSocketMessage, handle chat type:
if (parsed.type === 'chat') {
  const chatMsg = { userId: parsed.userId, text: parsed.payload as string, ts: parsed.ts };
  await this.appendMessage(chatMsg);
  // Broadcast to everyone including sender for confirmation
  for (const peer of this.ctx.getWebSockets()) {
    if (peer.readyState === WebSocket.OPEN) {
      peer.send(JSON.stringify({ type: 'chat', payload: chatMsg }));
    }
  }
}
```

---

## 6. Testing the Durable Object Locally

```bash
# Start the Worker with DO support
wrangler dev --local

# In a second terminal, open two WebSocket clients
wscat -c "ws://localhost:8787/ws?roomId=room-1"
# In a third terminal:
wscat -c "ws://localhost:8787/ws?roomId=room-1"
# Type JSON in one terminal and observe it appears in the other:
# > {"type":"chat","payload":"hello","userId":"alice","ts":1724342400000}
```

---

## Anti-Patterns

- **Using a stateless Worker to fan out WebSocket messages** — Workers do not share memory across invocations. Without a Durable Object there is no single place to track all sockets in a room; messages from one connection will not reach others.
- **Creating a new DO stub on every message** — stub lookup (`env.ROOM.get(id)`) is cheap but the DO instance itself must be the same for all clients in a room. Always derive the ID deterministically from the room identifier (`idFromName`), never `newUniqueId()`.
- **Sending binary ArrayBuffer when you mean JSON** — Durable Objects support binary WebSocket frames, but mixing string and binary payloads in the same connection complicates client handling. Standardise on JSON strings unless you have measured throughput requirements.
- **Not handling the `close` event in `webSocketClose`** — Failing to call `ws.close()` inside the handler leaks the socket in the DO's registry; `getWebSockets()` will keep returning the dead socket and you will broadcast to nothing.
- **Storing unbounded message history in DO storage** — Durable Object SQLite storage has a 10 GB limit per namespace. Trim arrays or use an alarm to prune old records.

---

## Gotchas

- **Hibernation requires `ctx.acceptWebSocket`** — If you use the old `ws.accept()` pattern the DO cannot hibernate; it stays active (and billable) even when idle. Migrate to `this.ctx.acceptWebSocket(server)`.
- **DO location pinning**: The first time a DO is invoked it is placed in the Cloudflare PoP nearest to that request. Subsequent requests are routed there globally. If your users span continents, consider sharding rooms by region to reduce latency.
- **WebSocket Pair ownership**: Only the `client` half of `WebSocketPair` is returned to the browser. The `server` half must be handed to the DO via `acceptWebSocket`. Never try to return both or call `accept()` on the client.
- **Reconnect and message ordering**: The Durable Object does not buffer messages sent during disconnects. Clients must request a state snapshot on reconnect (`type: 'sync'`) rather than relying on the message stream to be complete.
- **Wrangler dev vs production DO IDs**: `idFromName` in local dev produces different IDs than production because the account ID differs. Never persist or compare DO IDs across environments.

---

## Verification

```bash
# Deploy and check WebSocket upgrade succeeds
curl -i \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  https://realtime-rooms.your-subdomain.workers.dev/ws?roomId=test
# Expect: HTTP/1.1 101 Switching Protocols

# Check active connections (DO alarm approach)
wrangler tail realtime-rooms --format pretty
```

---

## Related

- `websocket-realtime-ui-patterns.md`
- `server-sent-events-streaming-ui.md`
- `react-query-cache-invalidation-workers-api-versioning.md`
- `zustand-workers-api-optimistic-updates.md`

---

## Sources

- Durable Objects — https://developers.cloudflare.com/durable-objects/
- WebSocket Hibernation API — https://developers.cloudflare.com/durable-objects/api/websockets/
- Cloudflare Workers WebSocket — https://developers.cloudflare.com/workers/runtime-apis/websockets/
