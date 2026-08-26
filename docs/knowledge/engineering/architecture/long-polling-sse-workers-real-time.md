# Long-Polling and Server-Sent Events on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your application needs to push updates from the server to a browser client — order status
changes, live scores, notification counts — but you cannot use WebSockets (firewall
restrictions, HTTP/2 proxies, or a client that does not support them). You need to choose
between long-polling and Server-Sent Events (SSE) and implement them reliably on Cloudflare
Workers backed by Durable Objects for state.

## Context

Three dominant patterns deliver server-initiated updates to browsers:

| Pattern        | Transport         | Bi-directional | Reconnect | Proxy-safe |
|----------------|-------------------|----------------|-----------|------------|
| WebSocket      | TCP upgrade       | Yes            | Manual    | Sometimes  |
| SSE            | HTTP chunked      | No (one-way)   | Automatic | Yes        |
| Long-polling   | HTTP request loop | No (one-way)   | Client    | Yes        |

**SSE** (`text/event-stream`) is a persistent HTTP response where the server writes data
frames as they become available. The browser's `EventSource` API handles reconnection
automatically. SSE works over HTTP/2 multiplexing.

**Long-polling** makes a normal HTTP request that the server holds open until an event is
available (or a timeout), then responds, and the client immediately opens a new request.
It works everywhere HTTP works and needs no special browser API.

On Workers, both patterns require a Durable Object to hold subscriber state — a plain
Worker is stateless and cannot block waiting for an event.

## SSE — Durable Object Broadcaster

The Durable Object maintains a `Map` of live SSE connections and fans out events using
a `TransformStream` per subscriber.

```typescript
// sse-broadcaster.ts
export class SSEBroadcaster extends DurableObject {
  private subscribers = new Map<string, WritableStreamDefaultWriter<Uint8Array>>();
  private encoder = new TextEncoder();

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === "/subscribe") {
      const id = crypto.randomUUID();
      const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
      const writer = writable.getWriter();
      this.subscribers.set(id, writer);

      // Send initial connection confirmation
      await writer.write(this.encode({ event: "connected", data: id }));

      // Clean up when the client disconnects
      req.signal.addEventListener("abort", () => {
        this.subscribers.delete(id);
        writer.close().catch(() => {});
      });

      return new Response(readable, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
          "X-Accel-Buffering": "no", // Disable Nginx buffering if behind a proxy
        },
      });
    }

    if (url.pathname === "/publish" && req.method === "POST") {
      const payload = await req.json<{ event: string; data: unknown }>();
      await this.broadcast(payload.event, payload.data);
      return Response.json({ sent: this.subscribers.size });
    }

    return new Response("Not Found", { status: 404 });
  }

  private async broadcast(event: string, data: unknown): Promise<void> {
    const frame = this.encode({ event, data });
    const dead: string[] = [];
    for (const [id, writer] of this.subscribers) {
      try {
        await writer.write(frame);
      } catch {
        dead.push(id);
      }
    }
    dead.forEach(id => this.subscribers.delete(id));
  }

  private encode({ event, data }: { event: string; data: unknown }): Uint8Array {
    return this.encoder.encode(
      `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
    );
  }
}
```

## SSE — Edge Worker Entry Point

The Edge Worker routes SSE subscribe requests to the correct DO shard by channel name.

```typescript
// sse-worker.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const channel = url.searchParams.get("channel");
    if (!channel) return new Response("Missing channel", { status: 400 });

    // Shard by channel so each channel has its own DO instance
    const id = env.SSE_BROADCASTER.idFromName(channel);
    const stub = env.SSE_BROADCASTER.get(id);
    return stub.fetch(req);
  },
};
```

Client-side connection:

```typescript
// client.ts (browser)
const source = new EventSource(`/sse?channel=order-${orderId}`);
source.addEventListener("order_updated", (e) => {
  const order = JSON.parse(e.data);
  renderOrder(order);
});
source.onerror = () => {
  // EventSource reconnects automatically after a 3 s backoff
  console.warn("SSE connection lost, reconnecting…");
};
```

## Long-Polling — Durable Object Hold

For clients that cannot use SSE (`EventSource` blocked), long-polling stores pending
event deliveries and resolves waiting requests.

```typescript
// long-poll-do.ts
export class LongPollDO extends DurableObject {
  private pendingEvents: unknown[] = [];
  private waiters: Array<(events: unknown[]) => void> = [];

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === "/poll") {
      const timeoutMs = Number(url.searchParams.get("timeout") ?? "20000");
      if (this.pendingEvents.length > 0) {
        const events = this.pendingEvents.splice(0);
        return Response.json({ events });
      }
      // Block until an event arrives or timeout elapses
      const events = await new Promise<unknown[]>((resolve) => {
        const timer = setTimeout(() => {
          this.waiters = this.waiters.filter(w => w !== resolve);
          resolve([]);
        }, Math.min(timeoutMs, 29_000)); // Stay within Worker CPU limit

        this.waiters.push((evts) => {
          clearTimeout(timer);
          resolve(evts);
        });
      });
      return Response.json({ events });
    }

    if (url.pathname === "/push" && req.method === "POST") {
      const event = await req.json();
      if (this.waiters.length > 0) {
        const waiter = this.waiters.shift()!;
        waiter([event]);
      } else {
        this.pendingEvents.push(event);
        // Cap buffer to avoid unbounded growth
        if (this.pendingEvents.length > 100) {
          this.pendingEvents.shift();
        }
      }
      return Response.json({ queued: this.pendingEvents.length });
    }

    return new Response("Not Found", { status: 404 });
  }
}
```

```typescript
// long-poll-worker.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const clientId = url.searchParams.get("clientId");
    if (!clientId) return new Response("Missing clientId", { status: 400 });
    const id = env.LONG_POLL_DO.idFromName(clientId);
    const stub = env.LONG_POLL_DO.get(id);
    return stub.fetch(req);
  },
};
```

Client-side polling loop:

```typescript
// poll-client.ts (browser)
async function pollForever(clientId: string): Promise<never> {
  while (true) {
    const res = await fetch(`/poll?clientId=${clientId}&timeout=20000`);
    const { events } = await res.json<{ events: unknown[] }>();
    events.forEach(renderEvent);
    // Immediately re-poll — server already waited for the timeout
  }
}
```

## Choosing Between SSE and Long-Polling

```typescript
// capability-detection.ts (browser)
function chooseTransport(): "sse" | "long-poll" {
  // EventSource is available in all modern browsers but may be blocked by proxies
  if (typeof EventSource !== "undefined") return "sse";
  return "long-poll";
}
```

Decision matrix for runtime use cases:

- **SSE**: dashboards, live feeds, notification badges — one-way push, many concurrent
  connections per channel, automatic reconnect required.
- **Long-polling**: legacy environments, HTTP/1.0 proxies, environments where persistent
  connections are blocked, or when you need guaranteed message delivery with server-side
  buffering.

## Anti-patterns

- Holding a long-poll request open for more than 29 s in a Worker. The CPU time wall-clock
  limit on paid plans is 30 s. Set `timeout` to ≤ 29_000 ms.
- Using a plain stateless Worker for SSE without a Durable Object — the Worker will
  terminate when the request finishes and cannot hold the stream open for pushed events.
- Sending large payloads (> 1 KB) on every SSE frame — use SSE for notification tokens
  and let the client fetch the full payload from a REST endpoint.
- Forgetting `X-Accel-Buffering: no` — Nginx and some CDN layers buffer chunked responses,
  breaking SSE entirely for clients behind them.
- Allowing unbounded `pendingEvents` growth in the long-poll DO — cap the buffer and
  log overflow to Analytics Engine.

## Gotchas

- The `req.signal` abort event fires when the client closes the connection, but only in
  Workers runtime ≥ 2024-09-02. Pin your compatibility date to at least that release.
- Durable Objects with active SSE connections hold an open WebSocket/stream in memory.
  If the DO is evicted (rare under normal load), all subscribers drop. Clients must
  detect the `onerror` / 0-event response and reconnect.
- Workers behind Cloudflare's own proxy always support SSE — the Cloudflare edge does
  not buffer `text/event-stream` responses.
- Long-poll DOs using `setTimeout` inside `Promise` constructors are safe because the
  `await` keeps the DO's CPU context alive. Do not use `ctx.waitUntil` for the hold.
- The `Last-Event-ID` SSE reconnect header is not handled automatically by the DO in
  this implementation. Add a `lastId` index to the subscriber state if ordered replay
  is required.

## Verification

1. Open DevTools → Network → filter `EventSource`. Confirm the `/sse?channel=X` request
   stays open and receives frames without 200 completion.
2. Kill the SSE connection from DevTools (cancel) and confirm the DO removes the subscriber
   within 5 s (check Analytics Engine subscriber count metric).
3. For long-polling: send a `/push` to the DO while a `/poll` request is pending; assert
   the poll resolves immediately with the event rather than waiting the full timeout.
4. Simulate a slow client (DevTools throttling) and confirm the broadcaster does not block
   other subscribers when one writer backpressures.

## Related

- `workers-do-websocket-architecture.md`
- `pubsub-durable-objects-websocket-broadcast.md`
- `polling-to-push-durable-objects-alarms.md`
- `real-time-streaming-architecture.md`
- `durable-object-alarm-api-scheduled-retry.md`

## Sources

- MDN EventSource: https://developer.mozilla.org/en-US/docs/Web/API/EventSource
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- SSE Specification (W3C): https://html.spec.whatwg.org/multipage/server-sent-events.html
- Cloudflare Workers Limits: https://developers.cloudflare.com/workers/platform/limits/
