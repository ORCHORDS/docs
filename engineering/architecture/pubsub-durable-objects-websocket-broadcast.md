# Pub-Sub Broadcast with Durable Objects and WebSockets

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need real-time fan-out of events to many subscribers—a collaborative document, a live scoreboard, a chat room—without a central message broker or a polling loop. Subscribers connect over WebSocket and expect sub-100 ms delivery of messages published by any client in the same topic.

## Context

Cloudflare Durable Objects provide a single-threaded, stateful actor that can hold many live WebSocket connections simultaneously via the WebSocket Hibernation API. Each DO instance acts as a topic's broker: publishers send an HTTP request to the DO, which broadcasts the payload to all active WebSocket connections. Because all sockets for a topic are co-located in the same DO, fan-out is a local in-memory operation with no network hop to a separate broker. The hibernation API allows the DO to sleep between messages, dramatically reducing costs compared to keeping the event loop alive.

## Topic Actor with Hibernation API

Use `state.acceptWebSocket(ws)` to hand the socket to the platform's hibernation layer. The DO can sleep between events; the platform wakes it on incoming messages or publishes.

```typescript
// src/actors/topic-broker.ts
interface PublishMessage {
  type: "publish";
  event: string;
  data: unknown;
}

export class TopicBroker implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Subscriber upgrades to WebSocket
    if (url.pathname === "/subscribe") {
      const upgradeHeader = request.headers.get("Upgrade");
      if (upgradeHeader !== "websocket") {
        return new Response("Expected WebSocket upgrade", { status: 426 });
      }
      const [client, server] = Object.values(new WebSocketPair()) as [WebSocket, WebSocket];
      // Hand off to hibernation — DO can sleep; woken on incoming message
      this.state.acceptWebSocket(server, [url.searchParams.get("clientId") ?? "anon"]);
      return new Response(null, { status: 101, webSocket: client });
    }

    // Publisher sends JSON payload via HTTP POST
    if (url.pathname === "/publish" && request.method === "POST") {
      const msg: PublishMessage = await request.json();
      this.broadcast(msg.event, msg.data);
      return Response.json({ delivered: this.state.getWebSockets().length });
    }

    return new Response("Not found", { status: 404 });
  }

  // Called by the platform when a hibernated WebSocket receives a message
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    if (typeof message !== "string") return;
    let parsed: PublishMessage;
    try {
      parsed = JSON.parse(message);
    } catch {
      ws.send(JSON.stringify({ error: "Invalid JSON" }));
      return;
    }
    if (parsed.type === "publish") {
      this.broadcast(parsed.event, parsed.data);
    }
  }

  async webSocketClose(ws: WebSocket, code: number): Promise<void> {
    ws.close(code, "Goodbye");
  }

  private broadcast(event: string, data: unknown): void {
    const frame = JSON.stringify({ event, data, ts: Date.now() });
    for (const ws of this.state.getWebSockets()) {
      try {
        ws.send(frame);
      } catch {
        // Socket already closed; hibernation will clean it up
      }
    }
  }
}
```

## Worker Entry Point and Topic Routing

Route subscribe and publish requests to the correct DO by topic name. Use `idFromName` so topic identity is stable across restarts and regions.

```typescript
// src/worker.ts
interface Env {
  TOPIC_BROKER: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const topic = url.searchParams.get("topic");
    if (!topic) {
      return new Response("Missing topic", { status: 400 });
    }

    // Stable actor per topic
    const id = env.TOPIC_BROKER.idFromName(topic);
    const broker = env.TOPIC_BROKER.get(id);

    // Forward subscribe or publish to the broker
    return broker.fetch(request);
  },
} satisfies ExportedHandler<Env>;
```

## Presence Tracking and Subscriber Metadata

Tag each WebSocket with metadata at accept time and use those tags for targeted delivery or presence lists. Tags survive hibernation and are accessible via `getWebSockets(tag)`.

```typescript
// Inside TopicBroker.fetch — subscribe path, extended
const tags = [
  `userId:${url.searchParams.get("userId") ?? "anon"}`,
  `channel:${url.searchParams.get("channel") ?? "default"}`,
];
this.state.acceptWebSocket(server, tags);

// Targeted broadcast to a single channel within the topic
private broadcastToChannel(channel: string, event: string, data: unknown): void {
  const frame = JSON.stringify({ event, data, ts: Date.now() });
  for (const ws of this.state.getWebSockets(`channel:${channel}`)) {
    try {
      ws.send(frame);
    } catch {
      // ignore closed sockets
    }
  }
}

// Presence: list connected user IDs
private getPresence(): string[] {
  return this.state
    .getWebSockets()
    .flatMap((ws) =>
      this.state
        .getTags(ws)
        .filter((t) => t.startsWith("userId:"))
        .map((t) => t.slice(7))
    );
}
```

## Anti-patterns

- Storing WebSocket references in plain instance variables without hibernation—the DO is evicted after ~30 seconds of inactivity, dropping all sockets.
- Using a single global DO for all topics at scale—a single actor is single-threaded and will serialise thousands of concurrent broadcasts; always shard by topic.
- Broadcasting from within `webSocketMessage` without debouncing high-frequency publishers—a single noisy client can saturate the actor's CPU quota.

## Gotchas

- `state.getWebSockets()` returns only sockets accepted on the current DO instance; if you migrate actors across Cloudflare's infrastructure (rare but possible), inflight sockets are dropped—clients must reconnect.
- The WebSocket hibernation API requires `wrangler.toml` to declare `compatibility_flags = ["websocket_hibernation_enabled"]` for older compatibility dates.

## Verification

```bash
# Open two subscriber connections in parallel
websocat "wss://your-worker.workers.dev/?topic=scores&clientId=alice" &
websocat "wss://your-worker.workers.dev/?topic=scores&clientId=bob" &

# Publish a message; both subscribers should receive it within ~50ms
curl -X POST "https://your-worker.workers.dev/?topic=scores" \
  -H "Content-Type: application/json" \
  -d '{"type":"publish","event":"goal","data":{"team":"home","score":1}}'
```

## Related

- `architecture/workers-do-websocket-architecture.md`
- `architecture/actor-model-durable-objects-workers.md`
- `architecture/event-driven-fanout-patterns.md`
- `architecture/competing-consumers-durable-objects.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/workers/runtime-apis/websockets/
