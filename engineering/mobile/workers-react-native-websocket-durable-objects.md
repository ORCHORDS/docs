# Real-time React Native App with WebSocket and Cloudflare Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need real-time bidirectional communication in a React Native app — chat, live scores, collaborative editing — and want a stateful server that keeps WebSocket sessions alive and broadcasts to all connected clients. Cloudflare Durable Objects give you a single-threaded, globally-consistent actor perfect for this pattern.

---

## Context
Cloudflare Workers can upgrade an HTTP request to a WebSocket (`Upgrade: websocket`) and then hand the socket to a Durable Object for long-lived state management. React Native ships a browser-compatible `WebSocket` global, so the client code is nearly identical to a web app. The Durable Object stores connected sockets in memory and uses its built-in `Storage` API for durable presence data. Reconnect logic with exponential backoff is essential because mobile networks are lossy and Workers can restart DOs during low-traffic periods.

---

## Setup / Config

```toml
# wrangler.toml
name = "rn-realtime"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[durable_objects.bindings]]
name = "CHAT_ROOM"
class_name = "ChatRoom"

[[migrations]]
tag = "v1"
new_classes = ["ChatRoom"]
```

---

## Implementation — Worker Entry Point

```typescript
// src/index.ts
import { ChatRoom } from './chat-room';
export { ChatRoom };

export interface Env {
  CHAT_ROOM: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Route /room/:id to the correct Durable Object
    const match = url.pathname.match(/^\/room\/([^/]+)$/);
    if (!match) {
      return new Response('Not found', { status: 404 });
    }

    const roomId = match[1];
    const id = env.CHAT_ROOM.idFromName(roomId);
    const stub = env.CHAT_ROOM.get(id);

    // Forward the entire request — including Upgrade header — to the DO
    return stub.fetch(request);
  },
};
```

---

## Implementation — Durable Object

```typescript
// src/chat-room.ts
export class ChatRoom implements DurableObject {
  private sessions: Map<string, WebSocket> = new Map();
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
    // Re-attach sockets that survived a hibernation wake (Workers Runtime feature)
    this.state.getWebSockets().forEach((ws) => {
      const meta = ws.deserializeAttachment() as { id: string };
      this.sessions.set(meta.id, ws);
    });
  }

  async fetch(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get('Upgrade');
    if (!upgradeHeader || upgradeHeader !== 'websocket') {
      return new Response('Expected WebSocket upgrade', { status: 426 });
    }

    const { 0: client, 1: server } = new WebSocketPair();
    const sessionId = crypto.randomUUID();

    // Accept with hibernation support so the DO can sleep between messages
    this.state.acceptWebSocket(server);
    server.serializeAttachment({ id: sessionId });
    this.sessions.set(sessionId, server);

    // Persist presence to durable storage
    await this.state.storage.put(`presence:${sessionId}`, {
      connectedAt: Date.now(),
      userAgent: request.headers.get('User-Agent') ?? 'unknown',
    });

    // Announce join to all other clients
    this.broadcast(JSON.stringify({ type: 'join', sessionId }), sessionId);

    return new Response(null, { status: 101, webSocket: client });
  }

  // Called by the runtime for each incoming WebSocket message
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const meta = ws.deserializeAttachment() as { id: string };
    const text = typeof message === 'string' ? message : new TextDecoder().decode(message);

    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      ws.send(JSON.stringify({ type: 'error', message: 'Invalid JSON' }));
      return;
    }

    // Echo back with attribution and broadcast to others
    this.broadcast(JSON.stringify({ type: 'message', from: meta.id, payload: parsed }));
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    const meta = ws.deserializeAttachment() as { id: string };
    this.sessions.delete(meta.id);
    await this.state.storage.delete(`presence:${meta.id}`);
    this.broadcast(JSON.stringify({ type: 'leave', sessionId: meta.id }));
  }

  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    const meta = ws.deserializeAttachment() as { id: string };
    this.sessions.delete(meta.id);
    await this.state.storage.delete(`presence:${meta.id}`);
    console.error('WebSocket error for session', meta.id, error);
  }

  private broadcast(message: string, excludeId?: string): void {
    for (const [id, ws] of this.sessions) {
      if (id !== excludeId) {
        try {
          ws.send(message);
        } catch {
          // Socket already closed; clean up lazily
          this.sessions.delete(id);
        }
      }
    }
  }
}
```

---

## Integration — React Native Client with Reconnect

```typescript
// hooks/useRoomSocket.ts
import { useEffect, useRef, useCallback, useState } from 'react';

const WORKERS_URL = 'wss://rn-realtime.<your-subdomain>.workers.dev';
const MAX_BACKOFF_MS = 30_000;

export function useRoomSocket(roomId: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [messages, setMessages] = useState<unknown[]>([]);
  const [status, setStatus] = useState<'connecting' | 'open' | 'closed'>('closed');

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(`${WORKERS_URL}/room/${roomId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      attemptRef.current = 0; // reset backoff on success
      setStatus('open');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string);
        setMessages((prev) => [...prev.slice(-199), data]); // keep last 200
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      setStatus('closed');
      scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [roomId]);

  const scheduleReconnect = useCallback(() => {
    const delay = Math.min(1_000 * 2 ** attemptRef.current, MAX_BACKOFF_MS);
    attemptRef.current += 1;
    timeoutRef.current = setTimeout(connect, delay);
  }, [connect]);

  const send = useCallback((payload: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      wsRef.current?.close(1000, 'unmount');
    };
  }, [connect]);

  return { messages, status, send };
}
```

---

## Anti-patterns
- **Storing WebSocket objects in DO `storage`** — sockets are in-memory handles; only metadata belongs in durable storage.
- **Opening a new WS per render** — always gate connection inside a `useEffect` with a stable dependency array.
- **Hardcoding linear retry intervals** — linear backoff floods the DO on reconnect storms; always use exponential + jitter.
- **Broadcasting inside `webSocketError` after the socket list is stale** — delete the session first, then broadcast the leave event.

---

## Gotchas
- DO hibernation closes all in-memory `sessions` entries; use `state.getWebSockets()` in the constructor to restore them.
- React Native's `WebSocket` does not support the `binaryType = 'arraybuffer'` property on all versions; prefer JSON text frames.
- Workers free tier limits Durable Objects to 100k requests/day; plan for paid usage with real-time apps.
- `WebSocketPair` is a Workers-only global — your unit tests must mock it or run inside `workerd` via Vitest.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Open two terminals and connect to the same room
wscat -c wss://rn-realtime.<subdomain>.workers.dev/room/lobby
# In a second terminal:
wscat -c wss://rn-realtime.<subdomain>.workers.dev/room/lobby
# Type in either; messages should appear in both.

# Check DO storage for presence entries
npx wrangler durable-objects storage list CHAT_ROOM --name lobby
```

---

## Related
- `workers-mobile-api-versioning-accept-header.md`
- `workers-flutter-d1-rest-api.md`

---

## Sources
- Cloudflare Durable Objects WebSocket Hibernation — https://developers.cloudflare.com/durable-objects/examples/websocket-hibernation-server/
- React Native WebSocket API — https://reactnative.dev/docs/network#websocket-support
- Exponential Backoff and Jitter (AWS) — https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
