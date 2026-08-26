# Shared Worker — Cloudflare Pages Background Sync

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

On example.com, users often open multiple tabs — a feed tab, a post detail tab, and a DM tab. Each tab independently polls the Cloudflare Workers API, sending redundant requests and making it hard to keep read/unread state consistent across tabs. A `SharedWorker` lets all same-origin tabs share a single background connection, deduplicate API polling, and broadcast state changes without a Service Worker's full offline-first complexity.

## Context

Cloudflare Pages serves the SPA shell statically. A `SharedWorker` script is bundled as a separate entry point and loaded from the same origin (`/workers/shared-sync.js`). Unlike `Dedicated Worker`, a `SharedWorker` lives as long as at least one tab holds a port to it. Vite handles the separate bundle entry; Cloudflare Pages caches the worker script at the CDN edge with long `max-age` headers.

## SharedWorker API Overview

A `SharedWorker` exposes a `MessagePort` interface. Each connecting tab receives its own `MessagePort` instance via the `connect` event on the worker side. The worker maintains a registry of all open ports and can fan-out messages to all tabs simultaneously.

```typescript
// src/workers/shared-sync.ts (compiled to /workers/shared-sync.js)

interface TabPort {
  id: string;
  port: MessagePort;
}

const ports: Map<string, TabPort> = new Map();
let pollInterval: ReturnType<typeof setInterval> | null = null;

self.addEventListener('connect', (event: MessageEvent) => {
  const port = (event as unknown as { ports: MessagePort[] }).ports[0];
  const tabId = crypto.randomUUID();

  ports.set(tabId, { id: tabId, port });

  port.addEventListener('message', (msg: MessageEvent) => {
    handleTabMessage(tabId, msg.data, port);
  });

  port.start();
  port.postMessage({ type: 'CONNECTED', tabId });

  if (!pollInterval) {
    startPolling();
  }
});
```

## Implementing the Polling Loop in the Worker

The worker owns one polling loop regardless of how many tabs are open. When a tab disconnects (its `MessagePort` closes), the worker removes it from the registry and stops polling when all tabs are gone.

```typescript
// Continued: src/workers/shared-sync.ts

const API_BASE = 'https://api.example.com';
let authToken: string | null = null;

function broadcast(message: unknown): void {
  for (const { port } of ports.values()) {
    try {
      port.postMessage(message);
    } catch {
      // Port is closed — will be cleaned up on next error
    }
  }
}

async function pollNotifications(): Promise<void> {
  if (!authToken) return;

  try {
    const response = await fetch(`${API_BASE}/v1/notifications/unread`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });

    if (!response.ok) return;
    const data = await response.json();
    broadcast({ type: 'NOTIFICATIONS_UPDATE', payload: data });
  } catch (err) {
    broadcast({ type: 'POLL_ERROR', error: String(err) });
  }
}

function startPolling(): void {
  pollInterval = setInterval(pollNotifications, 15_000);
  pollNotifications(); // immediate first run
}

function stopPolling(): void {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

function handleTabMessage(
  tabId: string,
  data: Record<string, unknown>,
  port: MessagePort
): void {
  switch (data.type) {
    case 'SET_AUTH_TOKEN':
      authToken = data.token as string;
      break;
    case 'MARK_READ':
      markNotificationsRead(data.ids as string[]);
      break;
    case 'DISCONNECT':
      ports.delete(tabId);
      if (ports.size === 0) stopPolling();
      port.close();
      break;
    default:
      port.postMessage({ type: 'UNKNOWN_COMMAND', received: data.type });
  }
}

async function markNotificationsRead(ids: string[]): Promise<void> {
  if (!authToken) return;
  await fetch(`${API_BASE}/v1/notifications/read`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${authToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ids }),
  });
  // Broadcast the updated read state to all tabs
  broadcast({ type: 'NOTIFICATIONS_MARKED_READ', ids });
}
```

## Connecting from the App — Tab Side

Each tab creates its own `SharedWorker` reference. The browser shares the underlying worker thread if one is already running for the same script URL and origin. Tabs register their auth token on startup and listen for broadcast updates.

```typescript
// src/lib/sync-worker-client.ts

type SyncMessage =
  | { type: 'CONNECTED'; tabId: string }
  | { type: 'NOTIFICATIONS_UPDATE'; payload: { count: number; items: unknown[] } }
  | { type: 'NOTIFICATIONS_MARKED_READ'; ids: string[] }
  | { type: 'POLL_ERROR'; error: string };

type SyncCommand =
  | { type: 'SET_AUTH_TOKEN'; token: string }
  | { type: 'MARK_READ'; ids: string[] }
  | { type: 'DISCONNECT' };

class SyncWorkerClient {
  private worker: SharedWorker | null = null;
  private port: MessagePort | null = null;
  private listeners: Array<(msg: SyncMessage) => void> = [];

  connect(): void {
    if (!('SharedWorker' in globalThis)) {
      console.warn('SharedWorker not supported — falling back to polling');
      return;
    }

    this.worker = new SharedWorker('/workers/shared-sync.js', {
      name: 'example project-sync',
      type: 'module',
    });

    this.port = this.worker.port;
    this.port.addEventListener('message', (event: MessageEvent<SyncMessage>) => {
      this.listeners.forEach((fn) => fn(event.data));
    });
    this.port.start();
  }

  send(command: SyncCommand): void {
    this.port?.postMessage(command);
  }

  on(listener: (msg: SyncMessage) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((fn) => fn !== listener);
    };
  }

  disconnect(): void {
    this.send({ type: 'DISCONNECT' });
    this.port?.close();
  }
}

export const syncWorker = new SyncWorkerClient();
```

## Cloudflare Pages Build Integration

Vite needs a separate entry point for the SharedWorker script so it is bundled independently with its own chunk hash.

```typescript
// vite.config.ts

import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        'shared-sync': 'src/workers/shared-sync.ts',
      },
      output: {
        entryFileNames: (chunk) =>
          chunk.name === 'shared-sync'
            ? 'workers/shared-sync.js' // stable URL for SharedWorker registration
            : 'assets/[name]-[hash].js',
      },
    },
  },
});
```

Cache the worker script aggressively in `public/_headers` since the URL is stable and content-addressed:

```
/workers/shared-sync.js
  Cache-Control: public, max-age=31536000, immutable
```

## Anti-patterns

- Fetching auth tokens directly from `localStorage` inside the SharedWorker — workers have no DOM access; pass the token via `postMessage`.
- Using a single global variable for the poll result without broadcasting — other tabs will not receive updates.
- Not handling `MessagePort` close errors when a tab is killed abruptly (`port.postMessage` throws `DOMException` if the port is dead).
- Registering a `SharedWorker` with a dynamic URL (e.g., including a hash in the filename) — this creates a new worker per navigation instead of sharing the existing one.
- Doing heavy CPU work in the worker's single thread, which blocks message handling and delays broadcasts to all tabs.

## Gotchas

- `SharedWorker` is not supported in Safari iOS (only macOS Safari 16.4+). Always implement a fallback polling path when `'SharedWorker' in globalThis` is `false`.
- The SharedWorker script must be served from the same origin as the connecting tabs — cross-origin SharedWorkers are not allowed.
- Workers loaded as `type: 'module'` do not fire the `connect` event using `self.onconnect = ...`; use `self.addEventListener('connect', ...)` instead.
- The worker persists until all `MessagePort`s are garbage-collected, not just closed. Explicitly call `port.close()` on disconnect.
- Cloudflare Pages CDN caches the worker script by URL. If you change the `output.entryFileNames` pattern to include a hash, existing connected tabs will continue using the cached worker until they reload.
- DevTools SharedWorker inspection is in `chrome://inspect/#workers` — not the standard DevTools panel.

## Verification

1. Open example.com in two browser tabs.
2. In `chrome://inspect/#workers`, confirm a single `example project-sync` worker appears.
3. In Tab 1, trigger a notification (e.g. via Postman to the Workers API).
4. Confirm both Tab 1 and Tab 2 receive the `NOTIFICATIONS_UPDATE` message within one poll cycle (≤15s).
5. Close Tab 1 — the worker should still run for Tab 2. Close Tab 2 — the worker should terminate.
6. In Safari on iOS, confirm the fallback polling path activates (`console.warn` appears in console).

## Related

- `browser-web-workers.md`
- `broadcastchannel-cross-tab-coordination.md`
- `web-locks-cross-context-coordination.md`
- `indexeddb-offline-sync-cloudflare-d1-workers.md`
- `pwa-service-worker-cloudflare-pages.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/SharedWorker
- https://developer.mozilla.org/en-US/docs/Web/API/MessagePort
- https://developers.cloudflare.com/pages/configuration/headers/
- https://vitejs.dev/config/build-options.html#build-rollupoptions
- https://html.spec.whatwg.org/multipage/workers.html#shared-workers
