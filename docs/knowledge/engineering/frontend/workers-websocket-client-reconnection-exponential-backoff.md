# Workers WebSocket Client Reconnection Exponential Backoff

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers WebSocket endpoint is working but the browser client drops the connection silently on network blips, mobile radio switches, or Workers restart events. Users see stale UI with no error. You need deterministic reconnection that does not hammer the server during outages.

## Context

Cloudflare Workers terminate WebSocket connections when the isolate recycles (~30 s idle default on the free tier; indefinite with Durable Objects keepalive). The browser `WebSocket` object fires `onclose` with code 1006 (abnormal) or 1001 (going away) and does not reconnect on its own. A naïve `new WebSocket(url)` inside `onclose` without backoff creates thundering-herd reconnect storms when hundreds of clients detect the same Workers cold-start.

Durable Objects hibernate (not terminate) WebSocket connections, so the server side survives; only the client transport drops. The reconnection strategy therefore needs to be entirely in browser code.

---

## 1. Core Reconnection State Machine

```typescript
// lib/reconnecting-ws.ts
export type RWSState = 'connecting' | 'open' | 'closing' | 'closed' | 'backing-off';

export interface RWSOptions {
  /** Initial delay in ms (default 250) */
  baseDelay?: number;
  /** Multiplier per attempt (default 2) */
  factor?: number;
  /** Maximum delay cap in ms (default 30_000) */
  maxDelay?: number;
  /** Jitter fraction 0–1 (default 0.25) */
  jitter?: number;
  /** Max reconnect attempts before giving up; 0 = infinite (default 0) */
  maxAttempts?: number;
  protocols?: string | string[];
}

export class ReconnectingWebSocket extends EventTarget {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private timerId: ReturnType<typeof setTimeout> | null = null;
  private _state: RWSState = 'closed';

  constructor(private readonly url: string | URL, private readonly opts: RWSOptions = {}) {
    super();
  }

  get state(): RWSState { return this._state; }
  get readyState(): number { return this.ws?.readyState ?? WebSocket.CLOSED; }

  connect(): void {
    if (this._state === 'open' || this._state === 'connecting') return;
    this._open();
  }

  send(data: string | ArrayBufferLike | Blob): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(data);
  }

  close(code = 1000, reason = ''): void {
    this._state = 'closing';
    clearTimeout(this.timerId ?? undefined);
    this.ws?.close(code, reason);
  }

  private _open(): void {
    this._state = 'connecting';
    const ws = new WebSocket(this.url, this.opts.protocols);
    this.ws = ws;

    ws.onopen = (ev) => {
      this.attempt = 0;
      this._state = 'open';
      this.dispatchEvent(new CustomEvent('open', { detail: ev }));
    };

    ws.onmessage = (ev) => {
      this.dispatchEvent(new MessageEvent('message', { data: ev.data }));
    };

    ws.onerror = (ev) => {
      this.dispatchEvent(new CustomEvent('error', { detail: ev }));
    };

    ws.onclose = (ev) => {
      this.dispatchEvent(new CustomEvent('close', { detail: ev }));
      if (this._state === 'closing') { this._state = 'closed'; return; }
      this._scheduleReconnect();
    };
  }

  private _scheduleReconnect(): void {
    const { baseDelay = 250, factor = 2, maxDelay = 30_000, jitter = 0.25, maxAttempts = 0 } = this.opts;
    if (maxAttempts > 0 && this.attempt >= maxAttempts) {
      this._state = 'closed';
      this.dispatchEvent(new CustomEvent('give-up', { detail: { attempts: this.attempt } }));
      return;
    }
    const exponential = Math.min(baseDelay * factor ** this.attempt, maxDelay);
    const noise = exponential * jitter * (Math.random() * 2 - 1);
    const delay = Math.max(0, exponential + noise);
    this.attempt++;
    this._state = 'backing-off';
    this.dispatchEvent(new CustomEvent('reconnecting', { detail: { attempt: this.attempt, delay } }));
    this.timerId = setTimeout(() => this._open(), delay);
  }
}
```

---

## 2. Visibility-Aware Pause / Resume

```typescript
// lib/visibility-ws.ts
import { ReconnectingWebSocket } from './reconnecting-ws';

/** Pause reconnections while the tab is hidden; resume on focus. */
export function withVisibilityGuard(rws: ReconnectingWebSocket): () => void {
  const onVisible = () => {
    if (rws.state === 'closed' || rws.state === 'backing-off') rws.connect();
  };
  const onHidden = () => {
    // Let the socket drain naturally; do not force-close so we catch pending frames.
  };
  document.addEventListener('visibilitychange', () =>
    document.hidden ? onHidden() : onVisible()
  );
  window.addEventListener('online', onVisible);
  return () => {
    document.removeEventListener('visibilitychange', onVisible);
    window.removeEventListener('online', onVisible);
  };
}
```

---

## 3. React Hook Integration

```typescript
// hooks/use-reconnecting-ws.ts
import { useEffect, useRef, useState, useCallback } from 'react';
import { ReconnectingWebSocket, RWSOptions, RWSState } from '../lib/reconnecting-ws';

export function useReconnectingWS(url: string, options?: RWSOptions) {
  const rwsRef = useRef<ReconnectingWebSocket | null>(null);
  const [state, setState] = useState<RWSState>('closed');
  const [lastMessage, setLastMessage] = useState<string | null>(null);

  useEffect(() => {
    const rws = new ReconnectingWebSocket(url, options);
    rwsRef.current = rws;

    rws.addEventListener('open', () => setState('open'));
    rws.addEventListener('close', () => setState(rws.state));
    rws.addEventListener('reconnecting', () => setState('backing-off'));
    rws.addEventListener('give-up', () => setState('closed'));
    rws.addEventListener('message', (ev) =>
      setLastMessage((ev as MessageEvent).data)
    );

    rws.connect();
    return () => rws.close();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  const send = useCallback((data: string) => rwsRef.current?.send(data), []);

  return { state, lastMessage, send };
}
```

---

## 4. Cloudflare Workers Endpoint (Durable Object Pair)

```typescript
// worker/chat-room.ts  (Durable Object)
export class ChatRoom implements DurableObject {
  private sessions = new Set<WebSocket>();

  async fetch(request: Request): Promise<Response> {
    const upgrade = request.headers.get('Upgrade');
    if (upgrade !== 'websocket') return new Response('Expected WebSocket', { status: 426 });

    const { 0: client, 1: server } = new WebSocketPair();
    this.ctx.acceptWebSocket(server);
    this.sessions.add(server);

    server.addEventListener('close', () => this.sessions.delete(server));
    server.addEventListener('message', (ev) => {
      for (const s of this.sessions) {
        if (s !== server && s.readyState === WebSocket.OPEN) s.send(ev.data);
      }
    });

    return new Response(null, { status: 101, webSocket: client });
  }
}
```

```typescript
// worker/index.ts
import { ChatRoom } from './chat-room';
export { ChatRoom };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const id = env.CHAT_ROOM.idFromName('global');
    const room = env.CHAT_ROOM.get(id);
    return room.fetch(request);
  },
} satisfies ExportedHandler<Env>;

interface Env { CHAT_ROOM: DurableObjectNamespace; }
```

---

## 5. Close-Code Classification

```typescript
// lib/ws-close-codes.ts
/** True when the browser should retry; false when the server explicitly ended. */
export function isRetriable(code: number): boolean {
  return (
    code === 1006 || // Abnormal closure (network drop, Workers restart)
    code === 1012 || // Service restart
    code === 1013 || // Try again later
    code === 1014    // Bad gateway
  );
}

// Use in ReconnectingWebSocket._open():
ws.onclose = (ev) => {
  this.dispatchEvent(new CustomEvent('close', { detail: ev }));
  if (this._state === 'closing') { this._state = 'closed'; return; }
  if (!isRetriable(ev.code)) { this._state = 'closed'; return; } // 1000/1001 = intentional
  this._scheduleReconnect();
};
```

---

## 6. Backoff Delay Curve Reference

| Attempt | base=250 factor=2 | With 25% jitter range |
|---------|-------------------|-----------------------|
| 0       | 250 ms            | 188–313 ms            |
| 1       | 500 ms            | 375–625 ms            |
| 2       | 1 000 ms          | 750 ms–1.25 s         |
| 3       | 2 000 ms          | 1.5–2.5 s             |
| 5       | 8 000 ms          | 6–10 s                |
| 7       | 30 000 ms (cap)   | 22.5–37.5 s (capped)  |

---

## Anti-patterns

- **Reconnecting on every close code** — code 1000 (normal) or 1001 (going away during navigation) should not trigger a retry; always check the close code.
- **No jitter** — fixed exponential backoff still creates correlated bursts; always add jitter.
- **Reconnecting while hidden** — connecting while the tab is invisible wastes Workers CPU budget and the connection is immediately dropped by Chrome's tab freezing.
- **Using `setInterval` for heartbeats inside the reconnection loop** — heartbeat timers survive the close and stack up across reconnection cycles; always clear them in `onclose`.

## Gotchas

- Workers free tier enforces a 100-second CPU limit per request; a WebSocket held open counts against this unless you use Durable Objects with hibernation (`ctx.acceptWebSocket`).
- `ev.code === 1006` means the TCP connection dropped without a WebSocket close frame; this is the most common code you will see from Workers restarts.
- Chrome 124+ freezes background tabs' WebSocket callbacks; reconnect logic that depends on timer precision will drift significantly when the tab is hidden.
- The `WebSocket` constructor in the browser throws a `SyntaxError` synchronously for invalid URLs; wrap `_open()` in try/catch or validate the URL before passing it.

## Verification

```bash
# Confirm Workers WebSocket upgrade is accepted
curl -i -N -H "Upgrade: websocket" \
  -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: $(openssl rand -base64 16)" \
  -H "Sec-WebSocket-Version: 13" \
  https://your-worker.workers.dev/ws
# Expect: HTTP/1.1 101 Switching Protocols

# Simulate a server drop by redeploying during an open connection:
wrangler deploy && wscat -c wss://your-worker.workers.dev/ws
# Client should print reconnecting… and reconnect within the first backoff window
```

## Related

- `websocket-durable-objects-realtime-ui.md`
- `websocket-realtime-ui-patterns.md`
- `server-sent-events-streaming-ui.md`
- `webtransport-cloudflare-workers-realtime.md`
- `browser-service-worker-cache.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/close_event
- https://www.rfc-editor.org/rfc/rfc6455#section-7.4.1
- https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
