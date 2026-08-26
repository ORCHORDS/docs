# Server-Sent Events Streaming from Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a real-time unidirectional data stream from the server to the browser — live dashboards, log tails, progress bars, notification feeds — without the overhead of WebSockets. Server-Sent Events (SSE) are the right primitive: they run over HTTP/1.1 or HTTP/2, reconnect automatically, and every browser supports the `EventSource` API natively. The challenge is implementing them correctly in a Cloudflare Worker where the execution model is event-driven rather than long-lived.

## Context

A Worker's default response model is request → response. Streaming requires holding the HTTP connection open while writing chunks to a `ReadableStream`. Cloudflare Workers support the WHATWG Streams API, so you can create a `TransformStream`, hold a reference to the writable side, and flush events as they occur. Each SSE event is a text frame with a specific wire format. The browser `EventSource` interprets these frames and exposes typed events. For fan-out — broadcasting one event to many connected clients — a Durable Object acts as the coordination hub, receiving producer messages and forwarding them to all open writer handles.

## Solution

```typescript
// worker.ts — SSE endpoint with Durable Object fan-out
import { DurableObject } from 'cloudflare:workers';

export interface Env {
  SSE_HUB: DurableObjectNamespace;
}

// ---- SSE wire-format helpers ----

function sseComment(text: string): string {
  return `: ${text}\n\n`;
}

function sseEvent(opts: {
  data: string;
  event?: string;
  id?: string;
  retry?: number;
}): string {
  const lines: string[] = [];
  if (opts.retry !== undefined) lines.push(`retry: ${opts.retry}`);
  if (opts.id !== undefined)    lines.push(`id: ${opts.id}`);
  if (opts.event !== undefined) lines.push(`event: ${opts.event}`);
  // data may contain newlines — each line must be prefixed
  for (const line of opts.data.split('\n')) {
    lines.push(`data: ${line}`);
  }
  return lines.join('\n') + '\n\n';
}

// ---- Worker fetch handler ----

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Producer: POST /publish?channel=X  { "type": "...", "payload": ... }
    if (request.method === 'POST' && url.pathname === '/publish') {
      const channel = url.searchParams.get('channel') ?? 'default';
      const id = env.SSE_HUB.idFromName(channel);
      const hub = env.SSE_HUB.get(id);
      return hub.fetch(request);
    }

    // Consumer: GET /stream?channel=X
    if (request.method === 'GET' && url.pathname === '/stream') {
      const channel = url.searchParams.get('channel') ?? 'default';
      const lastEventId = request.headers.get('Last-Event-ID') ?? undefined;

      const id = env.SSE_HUB.idFromName(channel);
      const hub = env.SSE_HUB.get(id);

      // Forward the subscribe request to the Durable Object
      const doRequest = new Request(request.url, {
        method: 'GET',
        headers: {
          ...Object.fromEntries(request.headers),
          'x-last-event-id': lastEventId ?? '',
        },
      });
      return hub.fetch(doRequest);
    }

    return new Response('Not found', { status: 404 });
  },
};

// ---- Durable Object: SSE fan-out hub ----

interface Subscriber {
  writer: WritableStreamDefaultWriter<Uint8Array>;
  connectedAt: number;
}

export class SseHub extends DurableObject {
  private subscribers = new Map<string, Subscriber>();
  private encoder = new TextEncoder();
  private eventCounter = 0;
  private keepaliveTimer: ReturnType<typeof setInterval> | null = null;

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    // Keepalive: send a comment every 20 s to prevent proxy timeouts
    this.keepaliveTimer = setInterval(() => {
      this.broadcast(sseComment('keepalive'), false);
    }, 20_000);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Producer path
    if (request.method === 'POST') {
      const body = await request.json<{ type: string; payload: unknown }>();
      this.eventCounter++;
      const frame = sseEvent({
        id: String(this.eventCounter),
        event: body.type,
        data: JSON.stringify(body.payload),
        retry: 3000, // tell browser to wait 3 s before reconnecting
      });
      await this.broadcast(frame, true);
      return new Response(JSON.stringify({ delivered: this.subscribers.size }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Subscriber path
    const subscriberId = crypto.randomUUID();
    const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
    const writer = writable.getWriter();

    this.subscribers.set(subscriberId, { writer, connectedAt: Date.now() });

    // Send preamble: last event id acknowledgement + initial comment
    const lastId = request.headers.get('x-last-event-id');
    let preamble = sseComment(`connected id=${subscriberId}`);
    if (lastId) {
      preamble += sseComment(`resuming after id=${lastId}`);
    }
    writer.write(this.encoder.encode(preamble)).catch(() => {
      this.removeSubscriber(subscriberId);
    });

    // Detect client disconnect via writer close
    writer.closed.then(() => {
      this.removeSubscriber(subscriberId);
    }).catch(() => {
      this.removeSubscriber(subscriberId);
    });

    return new Response(readable, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-store',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no', // disable Nginx proxy buffering if present
      },
    });
  }

  private async broadcast(frame: string, logErrors: boolean): Promise<void> {
    const encoded = this.encoder.encode(frame);
    const dead: string[] = [];

    for (const [id, sub] of this.subscribers) {
      try {
        await sub.writer.write(encoded);
      } catch {
        dead.push(id);
      }
    }

    for (const id of dead) {
      this.removeSubscriber(id);
      if (logErrors) console.warn(`[SseHub] removed dead subscriber ${id}`);
    }
  }

  private removeSubscriber(id: string): void {
    const sub = this.subscribers.get(id);
    if (sub) {
      sub.writer.close().catch(() => {});
      this.subscribers.delete(id);
    }
  }
}

// ---- Browser client ----
// (TypeScript, compiled and served separately)

/*
const es = new EventSource('/stream?channel=updates', { withCredentials: false });

es.addEventListener('order-update', (e: MessageEvent) => {
  const payload = JSON.parse(e.data) as { orderId: string; status: string };
  console.log('order update', payload);
});

es.addEventListener('error', () => {
  // EventSource reconnects automatically using the last received id
  console.warn('SSE connection lost, browser will retry...');
});

// Clean up when navigating away
window.addEventListener('beforeunload', () => es.close());
*/
```

## Implementation Details

**SSE wire format.** Each event is one or more `field: value` lines followed by a blank line. The `data:` field may appear multiple times (joined with `\n` by the browser). The `id:` field sets the `Last-Event-ID` which the browser sends on reconnect. The `retry:` field overrides the reconnect interval (milliseconds). A line starting with `:` is a comment and ignored by the browser but keeps the connection alive through intermediaries.

**Durable Object as fan-out hub.** Each channel maps to one DO instance (via `idFromName(channel)`). All subscribers for that channel share one DO. When the producer POSTs, the DO writes to every subscriber's `WritableStreamDefaultWriter`. The DO's single-threaded execution model prevents race conditions on the `subscribers` map.

**Graceful disconnect detection.** The `writer.closed` promise rejects or resolves when the writable end of the `TransformStream` closes — which happens when the Worker's runtime detects the client TCP connection is gone. This is more reliable than a ping-pong mechanism and adds no extra round-trips.

**Reconnection with `Last-Event-ID`.** The browser includes `Last-Event-ID` as an HTTP header on every reconnect. The Worker extracts it and can replay missed events from a Durable Object storage log (not shown here, but straightforward to add with `state.storage.list()`).

**`X-Accel-Buffering: no`.** Some reverse-proxy configurations (Nginx in front of Cloudflare) buffer responses. This header disables that at the Nginx layer and ensures events flush immediately.

## Anti-patterns

- **Polling with `setInterval` on the client** — defeats the purpose of SSE; use `EventSource`.
- **Returning a `ReadableStream` from the Worker without holding the writable side** — the stream closes immediately. Always store the `WritableStreamDefaultWriter` reference.
- **Sending JSON as the top-level SSE `data:` with newlines unescaped** — multi-line data requires every line prefixed with `data:`. The helper above handles this.
- **Forgetting `Cache-Control: no-cache`** — CDN or browser cache will serve a stale response instead of opening a new stream.
- **Using a single global DO for all channels** — creates a hot-spot. Shard by channel name.

## Gotchas

- **HTTP/2 multiplexing.** Over HTTP/2 each SSE connection is one stream inside a single TCP connection; keepalive comments are still recommended because load balancers may terminate idle HTTP/2 streams.
- **Cloudflare CPU limits.** A Durable Object has a 30-second CPU time limit per request, but streaming connections are not CPU-bound — they are I/O-bound and can remain open for minutes.
- **DO hibernation.** If the DO has no active connections it will be evicted; the `keepaliveTimer` inside the constructor prevents this while subscribers exist, but if the DO is evicted the `subscribers` map is reset to empty. Consider storing the last N events in DO storage so reconnecting clients can catch up.
- **`writer.write()` back-pressure.** The `await` on `writer.write()` respects back-pressure from a slow client. A slow subscriber will cause `broadcast` to stall until that subscriber drains. For high-throughput channels, use `writer.ready` with a timeout and drop lagging subscribers.

## Verification

```bash
# Start worker locally
npx wrangler dev

# In terminal 1: subscribe
curl -N http://localhost:8787/stream?channel=test

# In terminal 2: publish
curl -X POST http://localhost:8787/publish?channel=test \
  -H 'Content-Type: application/json' \
  -d '{"type":"ping","payload":{"msg":"hello"}}'

# Expected output in terminal 1:
# : connected id=<uuid>
# retry: 3000
# id: 1
# event: ping
# data: {"msg":"hello"}
#
```

## Related

- `documentation/categories/frontend/spa-history-api-routing.md` — client-side navigation that should reconnect the EventSource on route change
- `documentation/categories/frontend/workers-feature-flag-ui-injection.md` — flag change events can be delivered over SSE
- Cloudflare Durable Objects docs — hibernation API for long-lived connections

## Sources

- https://html.spec.whatwg.org/multipage/server-sent-events.html
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/workers/runtime-apis/streams/
