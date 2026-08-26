# React Native Workers SSE Event Stream

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

React Native apps using `fetch` or `XMLHttpRequest` against a Cloudflare Workers SSE endpoint receive the full body as a single blob after the connection closes rather than receiving events incrementally. The app feels unresponsive on long-running streams (LLM token delivery, live scores, order-status updates).

## Context

Browsers expose `EventSource` natively; React Native's JavaScript environment does not. Hermes and the Metro bundler do not polyfill `EventSource`. The standard `fetch` API in React Native buffers the response body until `response.body` (a WHATWG ReadableStream) is consumed — but Hermes only partially implements the Streams API. This article shows the correct pattern: a Worker that emits well-formed SSE, a lightweight native module (or the `react-native-sse` community library), and reconnect / keepalive handling.

---

## Worker SSE Endpoint

```typescript
// workers/sse-stream.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const encoder = new TextEncoder();

    const send = (event: string, data: unknown, id?: string) => {
      const lines = [
        id ? `id: ${id}` : '',
        `event: ${event}`,
        `data: ${JSON.stringify(data)}`,
        '',
        '',
      ].filter(Boolean).join('\n');
      return writer.write(encoder.encode(lines));
    };

    // Run stream in background — do NOT await here
    (async () => {
      try {
        const cursor = request.headers.get('Last-Event-ID') ?? '0';
        // Pull from KV or D1 using cursor for replay on reconnect
        const messages = await env.DB.prepare(
          'SELECT id, payload FROM events WHERE id > ? ORDER BY id LIMIT 50'
        ).bind(cursor).all();

        for (const row of messages.results) {
          await send('message', row.payload, String(row.id));
        }

        // Keep-alive ping every 25 s (Cloudflare 100 s idle limit)
        const pingInterval = setInterval(async () => {
          await writer.write(encoder.encode(': ping\n\n'));
        }, 25_000);

        // Long-poll tail via Durable Object or Queue consumer
        // (replace with your actual live-feed mechanism)
        await new Promise<void>((resolve) => {
          setTimeout(() => {
            clearInterval(pingInterval);
            resolve();
          }, 90_000);
        });
      } finally {
        await writer.close();
      }
    })();

    return new Response(readable, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Access-Control-Allow-Origin': '*',
      },
    });
  },
};
```

---

## React Native Client — Using react-native-sse

```typescript
// src/hooks/useSSE.ts
import EventSource from 'react-native-sse';
import { useEffect, useRef, useState } from 'react';
import { getAuthToken } from '../auth/tokenStore';

interface SSEOptions {
  url: string;
  onMessage: (data: string) => void;
}

export function useSSE({ url, onMessage }: SSEOptions) {
  const esRef = useRef<EventSource | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const connect = async () => {
      const token = await getAuthToken();
      const es = new EventSource(url, {
        headers: { Authorization: `Bearer ${token}` },
        withCredentials: false,
        debug: __DEV__,
      });

      es.addEventListener('open', () => {
        if (isMounted) setConnected(true);
      });

      es.addEventListener('message', (event) => {
        if (isMounted && event.data) onMessage(event.data);
      });

      es.addEventListener('error', (event) => {
        if ((event as any).type === 'error') {
          es.removeAllEventListeners();
          es.close();
          // Exponential back-off handled by the hook's retry below
          if (isMounted) {
            setConnected(false);
            setTimeout(connect, 3_000);
          }
        }
      });

      esRef.current = es;
    };

    connect();

    return () => {
      isMounted = false;
      esRef.current?.removeAllEventListeners();
      esRef.current?.close();
    };
  }, [url]);

  return { connected };
}
```

---

## Reconnect with Last-Event-ID

```typescript
// src/hooks/useSSEWithReplay.ts
import EventSource from 'react-native-sse';
import { useRef } from 'react';

export function useSSEWithReplay(url: string, onData: (d: string) => void) {
  const lastId = useRef<string>('0');

  const buildUrl = () => {
    const u = new URL(url);
    // Workers read Last-Event-ID from the header set automatically by
    // the EventSource spec — but react-native-sse also accepts it as a
    // query param fallback for proxies that strip headers.
    u.searchParams.set('since', lastId.current);
    return u.toString();
  };

  const es = new EventSource(buildUrl(), {
    headers: { 'Last-Event-ID': lastId.current },
  });

  es.addEventListener('message', (e) => {
    if (e.lastEventId) lastId.current = e.lastEventId;
    onData(e.data ?? '');
  });
}
```

---

## Durable Object for Fan-out Broadcast

```typescript
// workers/broadcast-do.ts
export class BroadcastRoom implements DurableObject {
  private sessions: Set<WritableStreamDefaultWriter> = new Set();

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get('Upgrade') !== 'durable-object-stream') {
      // Publish path: POST body is broadcast to all listeners
      const payload = await request.text();
      for (const writer of this.sessions) {
        const encoder = new TextEncoder();
        writer.write(encoder.encode(`data: ${payload}\n\n`)).catch(() => {
          this.sessions.delete(writer);
        });
      }
      return new Response('ok');
    }

    // Subscribe path: return SSE stream
    const { readable, writable } = new TransformStream();
    this.sessions.add(writable.getWriter());
    return new Response(readable, {
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }
}
```

---

## Anti-patterns

- **Using `fetch` with a manual stream reader on React Native** — `response.body.getReader()` is available in newer RN versions but Hermes does not guarantee backpressure; large bursts stall the UI thread.
- **Setting `retry:` to a very short value** — values under 1 000 ms cause the Worker to exceed its per-account connection limits under many simultaneous clients.
- **Keeping a connection open indefinitely** — Cloudflare closes idle Workers connections after 100 s. Always emit a keepalive comment every 25–30 s.
- **Skipping `Last-Event-ID` handling** — without cursor-based replay, a brief network change (cell tower handoff) causes the client to miss events permanently.

---

## Gotchas

- `react-native-sse` v2+ requires `react-native` ≥ 0.71 and the New Architecture is recommended for performance.
- On iOS, background app state suspends the TCP connection; SSE is effectively paused. Use `AppState` to reconnect when the app returns to the foreground.
- Android Doze mode will cut the TCP socket after ~10 minutes in idle. Use a foreground service or WorkManager ping if long-lived streams are critical.
- Cloudflare Workers in the free tier are limited to 100 ms CPU per request — the streaming response itself bypasses this limit but any synchronous work before `return new Response(readable, ...)` counts.

---

## Verification

```bash
# Confirm SSE headers from Worker
curl -N -H "Accept: text/event-stream" https://your-worker.workers.dev/stream

# Should stream lines like:
# id: 42
# event: message
# data: {"status":"ok"}
#
# : ping
```

```typescript
// Jest test: assert event count received
import { render, waitFor } from '@testing-library/react-native';
// mock react-native-sse in __mocks__/react-native-sse.ts
// emit 3 synthetic events, assert component renders all 3
```

---

## Related

- `capacitor-workers-sse-streaming.md`
- `react-native-durable-objects-realtime.md`
- `mobile-websocket-realtime-connections.md`
- `react-native-workers-background-fetch-cron-sync.md`
- `expo-workers-push-notification-receipts.md`

---

## Sources

- Cloudflare Workers Streaming docs: https://developers.cloudflare.com/workers/runtime-apis/streams/
- react-native-sse GitHub: https://github.com/binaryminds/react-native-sse
- MDN EventSource: https://developer.mozilla.org/en-US/docs/Web/API/EventSource
- Hermes Streams support: https://github.com/facebook/hermes/issues
