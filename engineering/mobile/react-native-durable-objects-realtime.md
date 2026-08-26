# React Native Real-Time Sync with Cloudflare Durable Objects WebSockets

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You need multiple React Native clients to share live mutable state — a collaborative whiteboard, a multi-player game room, a live order status board — with sub-second latency and no message fan-out gap between clients. You are already on Cloudflare Workers. A standard broadcast architecture using a stateless Worker + KV falls apart because KV has eventual consistency and stateless Workers cannot hold WebSocket connections across messages. You want a persistent server-side state object that proxies WebSocket connections and guarantees ordering without standing up a traditional Node/Socket.io server.

---

## Context

Cloudflare Durable Objects are single-instance, strongly consistent, globally co-located stateful compute units. Each Durable Object instance:

- Holds WebSocket connections alive via the Hibernation API (zero billing during idle time).
- Has a transactional key-value storage (`this.ctx.storage`) with ACID semantics.
- Is co-located with its storage in one Cloudflare data center — connection routing to the nearest instance adds one extra hop but eliminates the distributed-state problem.

The pattern is: React Native opens a WebSocket to `wss://api.example.com/room/{roomId}`. The Worker stub routes the upgrade to a Durable Object keyed by `roomId`. That object fans out messages to all connected clients.

---

## 1. Durable Object Worker

```toml
# wrangler.toml
name = "room-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[durable_objects.bindings]]
name = "ROOMS"
class_name = "Room"

[[migrations]]
tag = "v1"
new_classes = ["Room"]
```

```typescript
// src/index.ts
export { Room } from "./room";

export interface Env {
  ROOMS: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Expected path: /room/{roomId}/ws
    const match = url.pathname.match(/^\/room\/([^/]+)\/ws$/);
    if (!match) {
      return new Response("Not found", { status: 404 });
    }

    const roomId = match[1];
    if (!roomId || roomId.length > 64) {
      return new Response("Invalid room ID", { status: 400 });
    }

    // Derive a stable DO id from the room slug
    const id = env.ROOMS.idFromName(roomId);
    const stub = env.ROOMS.get(id);
    return stub.fetch(request);
  },
};
```

---

## 2. Durable Object Implementation

```typescript
// src/room.ts
import { DurableObject } from "cloudflare:workers";

interface ClientMessage {
  type: "state_patch" | "cursor" | "ping";
  payload: unknown;
  clientId: string;
}

interface ServerMessage {
  type: "state_patch" | "cursor" | "error" | "pong" | "init";
  payload: unknown;
  from?: string;
  ts: number;
}

export class Room extends DurableObject {
  // Hibernation API: the DO sleeps between messages, connections persist
  constructor(ctx: DurableObjectState, env: never) {
    super(ctx, env);
    this.ctx.setWebSocketAutoResponse(
      new WebSocketRequestResponsePair("ping", "pong")
    );
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const { 0: client, 1: server } = new WebSocketPair();
    const clientId = crypto.randomUUID();

    this.ctx.acceptWebSocket(server, [clientId]);

    // Send current room state to the new client
    const state = (await this.ctx.storage.get<unknown>("state")) ?? {};
    const initMsg: ServerMessage = {
      type: "init",
      payload: state,
      ts: Date.now(),
    };
    server.send(JSON.stringify(initMsg));

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, raw: string | ArrayBuffer): Promise<void> {
    if (typeof raw !== "string") return;

    let msg: ClientMessage;
    try {
      msg = JSON.parse(raw);
    } catch {
      ws.send(
        JSON.stringify({ type: "error", payload: "Invalid JSON", ts: Date.now() })
      );
      return;
    }

    if (msg.type === "state_patch") {
      // Merge the patch into persistent state
      const current = (await this.ctx.storage.get<Record<string, unknown>>("state")) ?? {};
      const merged = { ...current, ...(msg.payload as object) };
      await this.ctx.storage.put("state", merged);

      // Broadcast to all other connected clients
      this.broadcast(ws, {
        type: "state_patch",
        payload: msg.payload,
        from: msg.clientId,
        ts: Date.now(),
      });
    }

    if (msg.type === "cursor") {
      // Ephemeral — broadcast without persisting
      this.broadcast(ws, {
        type: "cursor",
        payload: msg.payload,
        from: msg.clientId,
        ts: Date.now(),
      });
    }
  }

  async webSocketClose(ws: WebSocket, code: number): Promise<void> {
    ws.close(code);
  }

  private broadcast(sender: WebSocket, msg: ServerMessage): void {
    const text = JSON.stringify(msg);
    for (const client of this.ctx.getWebSockets()) {
      if (client !== sender && client.readyState === WebSocket.READY_STATE_OPEN) {
        try {
          client.send(text);
        } catch {
          // client disconnected between getWebSockets() and send()
        }
      }
    }
  }
}
```

---

## 3. React Native WebSocket Client Hook

```typescript
// src/hooks/useDurableRoom.ts
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import NetInfo from "@react-native-community/netinfo";

const WS_URL = "wss://api.example.com";
const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 30_000;
const PING_INTERVAL_MS = 25_000;  // keep-alive inside Cloudflare's 60s WS idle limit

interface RoomState {
  connected: boolean;
  state: Record<string, unknown>;
  sendPatch: (patch: Record<string, unknown>) => void;
  sendCursor: (cursor: unknown) => void;
}

export function useDurableRoom(roomId: string, clientId: string): RoomState {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(RECONNECT_BASE_MS);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const [connected, setConnected] = useState(false);
  const [state, setState] = useState<Record<string, unknown>>({});

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_URL}/room/${roomId}/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      reconnectDelay.current = RECONNECT_BASE_MS;

      // Start keep-alive pings
      pingTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = (event) => {
      if (event.data === "pong") return;  // handled by Durable Object auto-response

      try {
        const msg = JSON.parse(event.data);

        if (msg.type === "init") {
          setState(msg.payload as Record<string, unknown>);
        } else if (msg.type === "state_patch" && msg.from !== clientId) {
          setState((prev) => ({ ...prev, ...(msg.payload as object) }));
        }
        // cursor messages are handled by a separate subscription in the UI layer
      } catch {
        console.warn("[useDurableRoom] parse error", event.data);
      }
    };

    ws.onerror = (err) => {
      console.error("[useDurableRoom] WS error", err);
    };

    ws.onclose = () => {
      setConnected(false);
      clearInterval(pingTimer.current!);

      // Exponential back-off
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(
          reconnectDelay.current * 2,
          RECONNECT_MAX_MS
        );
        connect();
      }, reconnectDelay.current);
    };
  }, [roomId, clientId]);

  useEffect(() => {
    connect();

    // Reconnect on network change
    const unsubscribe = NetInfo.addEventListener((netState) => {
      if (netState.isConnected && wsRef.current?.readyState !== WebSocket.OPEN) {
        clearTimeout(reconnectTimer.current!);
        reconnectDelay.current = RECONNECT_BASE_MS;
        connect();
      }
    });

    return () => {
      clearTimeout(reconnectTimer.current!);
      clearInterval(pingTimer.current!);
      wsRef.current?.close(1000, "unmount");
      unsubscribe();
    };
  }, [connect]);

  const sendPatch = useCallback(
    (patch: Record<string, unknown>) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(
        JSON.stringify({ type: "state_patch", payload: patch, clientId })
      );
      // Optimistic update
      setState((prev) => ({ ...prev, ...patch }));
    },
    [clientId]
  );

  const sendCursor = useCallback(
    (cursor: unknown) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(
        JSON.stringify({ type: "cursor", payload: cursor, clientId })
      );
    },
    [clientId]
  );

  return { connected, state, sendPatch, sendCursor };
}
```

---

## 4. Usage in a Screen

```typescript
// screens/CollaborativeBoard.tsx
import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { useDurableRoom } from "../hooks/useDurableRoom";

const ROOM_ID = "board-abc123";
const CLIENT_ID = "user-456";   // from auth context in production

export default function CollaborativeBoard() {
  const { connected, state, sendPatch } = useDurableRoom(ROOM_ID, CLIENT_ID);

  const incrementCounter = () => {
    const current = (state.counter as number) ?? 0;
    sendPatch({ counter: current + 1 });
  };

  return (
    <View style={styles.container}>
      <Text style={styles.status}>
        {connected ? "Live" : "Reconnecting…"}
      </Text>
      <Text style={styles.counter}>{(state.counter as number) ?? 0}</Text>
      <TouchableOpacity onPress={incrementCounter} style={styles.button}>
        <Text>+1</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center" },
  status: { fontSize: 12, color: "#888", marginBottom: 8 },
  counter: { fontSize: 64, fontWeight: "700", marginBottom: 24 },
  button: {
    padding: 16,
    backgroundColor: "#0066cc",
    borderRadius: 8,
  },
});
```

---

## 5. Authentication and Room Access Control

Add a JWT check in the stub Worker before forwarding to the Durable Object:

```typescript
// src/index.ts (extended)
async function authenticate(request: Request): Promise<string | null> {
  const auth = request.headers.get("Authorization");
  if (!auth?.startsWith("Bearer ")) return null;
  const token = auth.slice(7);

  try {
    // Verify using Cloudflare Workers crypto
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // Minimal JWT verification — use a full library in production
    const payload = JSON.parse(atob(parts[1]));
    if (payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload.sub as string;
  } catch {
    return null;
  }
}
```

Pass the authenticated `userId` as a query param to the DO, where it is stored in `WebSocket` tags alongside `clientId` for presence tracking.

---

## Anti-Patterns

- **Using stateless Workers to broadcast WebSocket messages.** Without Durable Objects, two clients connected to different Worker instances never receive each other's messages.
- **Persisting every cursor position to DO storage.** Storage writes are synchronous and count against storage billing. Cursor positions are ephemeral — fan them out in memory only.
- **Assuming one DO instance per user.** DO instances are keyed by room/entity, not by user. A single user reconnecting creates the same DO instance; a new room creates a new one.
- **Not implementing the ping keep-alive.** Cloudflare closes idle WebSocket connections after 60 seconds. Client pings at 25 s prevent the closure without billing the DO for idle CPU.
- **Not handling `WebSocket.READY_STATE_OPEN` before send.** Calling `.send()` on a closing socket throws a `InvalidStateError` that can crash the React Native JS thread.

---

## Gotchas

- **DO co-location latency.** A user in Tokyo connecting to a room whose DO is co-located in London will see higher latency. Cloudflare does not yet support full DO migration. Mitigate by creating room IDs with a region prefix and routing based on the user's CF-IPCountry header.
- **Storage size limit per DO.** Each Durable Object can store up to 128 KB per key and up to 10 GB total. For large collaborative documents, store the document in R2 and use the DO only for the operational transform log.
- **React Native does not support the `WebSocket` Hibernation API client-side.** This is a server-side Cloudflare concept; the React Native WebSocket API is standard — no changes needed on the client.
- **DO alarms and WebSocket Hibernation do not mix.** If you use `setAlarm()` inside a DO that also uses hibernation, the alarm wakes the DO but previously hibernated WebSockets must be re-iterated via `this.ctx.getWebSockets()`.
- **Expo Go blocks custom WebSocket headers.** In Expo Go the `WebSocket` constructor accepts headers only in newer SDK versions. Use a development build via EAS Build to test authenticated WebSocket connections.

---

## Verification

```bash
# 1. Deploy the Worker + Durable Object
wrangler deploy

# 2. Open two WebSocket connections to the same room
wscat -c "wss://room-api.example.workers.dev/room/test-room/ws"
# In a second terminal:
wscat -c "wss://room-api.example.workers.dev/room/test-room/ws"

# 3. Send a patch from terminal 1 — verify it arrives in terminal 2
# In terminal 1: {"type":"state_patch","payload":{"x":42},"clientId":"c1"}

# 4. Inspect DO storage via Wrangler
wrangler d1 execute room-api --command "SELECT * FROM sqlite_master"
# (DO storage is not directly inspectable but tailable via wrangler tail)

# 5. Tail Worker logs
wrangler tail room-api --format pretty
```

---

## Related

- `mobile-websocket-realtime-connections.md`
- `mobile-offline-first-sync-cloudflare-queues.md`
- `react-native-netinfo.md`
- `cloudflare-workers-ai-mobile-inference-edge.md`
- `mobile-network-resilience-cloudflare-workers.md`

---

## Sources

- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Durable Objects WebSocket Hibernation — https://developers.cloudflare.com/durable-objects/examples/websocket-hibernation/
- React Native WebSocket API — https://reactnative.dev/docs/network#websocket-support
- `@react-native-community/netinfo` — https://github.com/react-native-netinfo/react-native-netinfo
- Cloudflare Workers WebSocket API — https://developers.cloudflare.com/workers/runtime-apis/websockets/
