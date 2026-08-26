# Playwright Workers WebSocket Durable Objects E2E Test
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You have a Cloudflare Worker that upgrades HTTP connections to WebSocket and delegates them to a
Durable Object for stateful fan-out (e.g. a chat room, collaborative editor, or live dashboard).
Unit tests with Miniflare confirm the DO logic, but you need a full E2E test that drives a real
browser through connection → message exchange → disconnect and asserts on both the client DOM and
server-side DO state.

## Context
Playwright's `page.evaluate` and its `WebSocket` API let you open a WebSocket from inside a
headless browser frame. Combined with a Wrangler dev server (`wrangler dev --local`) or a deployed
preview URL, you can write deterministic tests against the full request path: TLS upgrade, Durable
Object routing, hibernation wake, and broadcast. The key challenge is synchronising async server
events with Playwright's polling model.

## Project Layout
```
workers/
  src/
    index.ts          # fetch handler – upgrades to WS
    chat-room.ts      # Durable Object – stateful broadcast
  wrangler.toml
e2e/
  websocket-chat.spec.ts
  helpers/
    ws-page.ts        # typed wrapper around page.evaluate WebSocket
playwright.config.ts
```

## Wrangler Config and Worker Source
`wrangler.toml`:
```toml
name = "chat-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[durable_objects.bindings]]
name = "CHAT_ROOM"
class_name = "ChatRoom"

[[migrations]]
tag = "v1"
new_classes = ["ChatRoom"]
```

`src/index.ts`:
```typescript
import { ChatRoom } from './chat-room';
export { ChatRoom };

export default {
  async fetch(req: Request, env: { CHAT_ROOM: DurableObjectNamespace }): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname.startsWith('/ws/')) {
      const roomId = url.pathname.split('/')[2] ?? 'default';
      const id = env.CHAT_ROOM.idFromName(roomId);
      const stub = env.CHAT_ROOM.get(id);
      return stub.fetch(req);
    }
    return new Response('OK');
  },
};
```

`src/chat-room.ts`:
```typescript
import { DurableObject } from 'cloudflare:workers';

export class ChatRoom extends DurableObject {
  private sessions = new Set<WebSocket>();

  async fetch(req: Request): Promise<Response> {
    const { 0: client, 1: server } = new WebSocketPair();
    this.ctx.acceptWebSocket(server);
    this.sessions.add(server);
    return new Response(null, { status: 101, webSocket: client });
  }

  webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
    const text = typeof message === 'string' ? message : new TextDecoder().decode(message);
    for (const session of this.sessions) {
      if (session !== ws && session.readyState === WebSocket.OPEN) {
        session.send(JSON.stringify({ from: 'peer', text }));
      }
    }
    ws.send(JSON.stringify({ echo: text }));
  }

  webSocketClose(ws: WebSocket): void {
    this.sessions.delete(ws);
  }
}
```

## Playwright Helper
`e2e/helpers/ws-page.ts`:
```typescript
import { Page } from '@playwright/test';

export interface WsHandle {
  send(msg: string): Promise<void>;
  receive(timeoutMs?: number): Promise<string>;
  close(): Promise<void>;
}

/**
 * Opens a WebSocket from within the browser page context.
 * Messages are buffered in a JS array on the window object so Playwright
 * can poll them without race conditions.
 */
export async function openWs(page: Page, url: string): Promise<WsHandle> {
  const key = `_ws_${Date.now()}`;
  await page.evaluate(
    ({ wsUrl, bufKey }: { wsUrl: string; bufKey: string }) => {
      const ws = new WebSocket(wsUrl);
      (window as Record<string, unknown>)[bufKey] = { ws, msgs: [] as string[], open: false };
      ws.onopen = () => { (window as Record<string, unknown>)[bufKey].open = true; };
      ws.onmessage = (e: MessageEvent) => {
        (window as Record<string, unknown>)[bufKey].msgs.push(e.data as string);
      };
    },
    { wsUrl: url, bufKey: key },
  );

  // Wait for connection to open
  await page.waitForFunction(
    (k: string) => (window as Record<string, unknown>)[k]?.open === true,
    key,
    { timeout: 5000 },
  );

  return {
    async send(msg: string) {
      await page.evaluate(
        ({ k, m }: { k: string; m: string }) => {
          (window as Record<string, unknown>)[k].ws.send(m);
        },
        { k: key, m: msg },
      );
    },
    async receive(timeoutMs = 5000): Promise<string> {
      await page.waitForFunction(
        (k: string) => ((window as Record<string, unknown>)[k]?.msgs as string[]).length > 0,
        key,
        { timeout: timeoutMs },
      );
      return page.evaluate((k: string) => {
        return ((window as Record<string, unknown>)[k].msgs as string[]).shift()!;
      }, key);
    },
    async close() {
      await page.evaluate((k: string) => {
        (window as Record<string, unknown>)[k].ws.close();
      }, key);
    },
  };
}
```

## E2E Spec
`e2e/websocket-chat.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';
import { openWs } from './helpers/ws-page';

const BASE_URL = process.env.WORKER_URL ?? 'http://localhost:8787';
const WS_BASE = BASE_URL.replace(/^http/, 'ws');

test.describe('ChatRoom Durable Object WebSocket E2E', () => {
  test('echo: worker echoes message back to sender', async ({ page }) => {
    await page.goto(BASE_URL);
    const ws = await openWs(page, `${WS_BASE}/ws/room-echo`);

    await ws.send('hello world');
    const reply = await ws.receive();
    expect(JSON.parse(reply)).toMatchObject({ echo: 'hello world' });

    await ws.close();
  });

  test('broadcast: second client receives message from first', async ({ browser }) => {
    const ctx1 = await browser.newContext();
    const ctx2 = await browser.newContext();
    const page1 = await ctx1.newPage();
    const page2 = await ctx2.newPage();

    await page1.goto(BASE_URL);
    await page2.goto(BASE_URL);

    const ws1 = await openWs(page1, `${WS_BASE}/ws/room-broadcast`);
    const ws2 = await openWs(page2, `${WS_BASE}/ws/room-broadcast`);

    await ws1.send('greetings from client 1');
    const broadcast = await ws2.receive();
    expect(JSON.parse(broadcast)).toMatchObject({ from: 'peer', text: 'greetings from client 1' });

    await ws1.close();
    await ws2.close();
    await ctx1.close();
    await ctx2.close();
  });

  test('reconnect: client can reconnect to same room after disconnect', async ({ page }) => {
    await page.goto(BASE_URL);
    const roomUrl = `${WS_BASE}/ws/room-reconnect`;

    const ws1 = await openWs(page, roomUrl);
    await ws1.send('first connection');
    const r1 = await ws1.receive();
    expect(JSON.parse(r1).echo).toBe('first connection');
    await ws1.close();

    const ws2 = await openWs(page, roomUrl);
    await ws2.send('second connection');
    const r2 = await ws2.receive();
    expect(JSON.parse(r2).echo).toBe('second connection');
    await ws2.close();
  });
});
```

`playwright.config.ts` (relevant excerpt):
```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: process.env.WORKER_URL ?? 'http://localhost:8787' },
  webServer: {
    command: 'wrangler dev --local --port 8787',
    url: 'http://localhost:8787',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
```

## Anti-patterns
- **Polling `page.evaluate` in a tight loop** – use `waitForFunction` instead; tight loops
  saturate the CDP pipe and produce flaky timeouts.
- **Sharing a single browser context across WS clients** – WebSocket connections from the same
  context share cookies and may be routed to the same DO instance unexpectedly; always open a
  fresh context per logical user.
- **Hard-coding sleep after `ws.send`** – the DO fan-out is async; always wait on `receive()` with
  a reasonable timeout.
- **Not closing contexts in `afterAll`** – leaked browser contexts accumulate over test runs in CI
  and exhaust available ports.

## Gotchas
- `wrangler dev --local` binds to `http://localhost:8787` but the WS URL must use `ws://`; replace
  the protocol prefix before passing to `new WebSocket()`.
- Durable Object WebSocket hibernation (`ctx.acceptWebSocket`) is only available in local mode with
  `wrangler` ≥ 3.40.0. Older versions silently fall back to in-memory sockets that do not survive
  a DO eviction, breaking reconnect tests.
- Playwright's `webServer` block kills and restarts `wrangler dev` on every full test run; add
  `reuseExistingServer: true` locally to save ~5 s of cold-start per suite.

## Verification
```bash
# Run against local wrangler dev server
npx playwright test e2e/websocket-chat.spec.ts

# Run against a deployed preview
WORKER_URL=https://chat-worker.<account>.workers.dev \
  npx playwright test e2e/websocket-chat.spec.ts --headed
```

## Related
- `durable-objects-websocket-hibernation-testing.md`
- `miniflare-multi-worker-environment-setup.md`
- `playwright-cloudflare-pages-e2e.md`
- `playwright-network-interception.md`
- `websocket-realtime-testing.md`

## Sources
- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://playwright.dev/docs/api/class-page#page-evaluate
- https://playwright.dev/docs/test-webserver
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
