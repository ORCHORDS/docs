# Playwright Workers WebSocket Real-Time E2E

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Anonymous social platforms like example project / example.com rely on live WebSocket connections for real-time features: vote counts ticking up, comment threads updating, and presence indicators showing how many anonymous users are viewing a post. Standard HTTP-oriented Playwright tests cannot assert on messages that arrive over a persistent WebSocket connection without additional plumbing to intercept and capture frames.

## Context

Cloudflare Workers implement WebSocket server-side via the WebSocket Hibernation API backed by Durable Objects. From the browser's perspective the connection is a standard WebSocket to a Workers URL; Playwright's CDP layer exposes a `page.on("websocket", ...)` event that captures all frames without modifying the application code. Tests run against a locally deployed Worker (`wrangler dev --local`) or a preview deployment.

## Test Setup

Configure Playwright to target the local `wrangler dev` server, with a global setup that boots the Worker:

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:8787",
    trace: "on-first-retry",
  },
  webServer: {
    command: "wrangler dev --local --port 8787",
    url: "http://localhost:8787",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
```

Create a typed helper for collecting WebSocket frames:

```typescript
// e2e/helpers/ws-collector.ts
import type { Page, WebSocket } from "@playwright/test";

export interface WsFrame {
  direction: "sent" | "received";
  payload: string;
  timestamp: number;
}

export function collectWsFrames(page: Page): {
  frames: WsFrame[];
  waitForFrame: (
    predicate: (f: WsFrame) => boolean,
    timeout?: number
  ) => Promise<WsFrame>;
} {
  const frames: WsFrame[] = [];
  const listeners: Array<(f: WsFrame) => void> = [];

  function push(f: WsFrame) {
    frames.push(f);
    listeners.forEach((l) => l(f));
  }

  page.on("websocket", (ws: WebSocket) => {
    ws.on("framesent", (e) =>
      push({ direction: "sent", payload: e.payload as string, timestamp: Date.now() })
    );
    ws.on("framereceived", (e) =>
      push({ direction: "received", payload: e.payload as string, timestamp: Date.now() })
    );
  });

  function waitForFrame(
    predicate: (f: WsFrame) => boolean,
    timeout = 5_000
  ): Promise<WsFrame> {
    const existing = frames.find(predicate);
    if (existing) return Promise.resolve(existing);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Timeout waiting for WS frame")),
        timeout
      );
      listeners.push((f) => {
        if (predicate(f)) {
          clearTimeout(timer);
          resolve(f);
        }
      });
    });
  }

  return { frames, waitForFrame };
}
```

## Test Cases

```typescript
// e2e/realtime-votes.test.ts
import { test, expect } from "@playwright/test";
import { collectWsFrames } from "./helpers/ws-collector";

test.describe("real-time vote updates", () => {
  test("vote count increments when another client votes", async ({
    page,
    context,
  }) => {
    const { frames, waitForFrame } = collectWsFrames(page);

    // First client opens a post
    await page.goto("/post/abc123");
    await page.waitForSelector("[data-ws-status='connected']");

    // Second client (separate browser context) casts a vote
    const page2 = await context.newPage();
    await page2.goto("/post/abc123");
    await page2.locator("[data-testid='upvote-btn']").click();
    await page2.close();

    // First client must receive a vote-update frame
    const frame = await waitForFrame(
      (f) =>
        f.direction === "received" &&
        JSON.parse(f.payload).type === "vote_update",
      8_000
    );

    const msg = JSON.parse(frame.payload);
    expect(msg.postId).toBe("abc123");
    expect(msg.delta).toBe(1);
    expect(msg.totalVotes).toBeGreaterThan(0);
  });

  test("presence count broadcasts when a new anonymous user joins", async ({
    page,
    context,
  }) => {
    const { waitForFrame } = collectWsFrames(page);

    await page.goto("/post/abc123");
    await page.waitForSelector("[data-ws-status='connected']");

    // A second user joins
    const page2 = await context.newPage();
    await page2.goto("/post/abc123");

    const frame = await waitForFrame(
      (f) =>
        f.direction === "received" &&
        JSON.parse(f.payload).type === "presence",
      6_000
    );

    const msg = JSON.parse(frame.payload);
    expect(msg.viewers).toBeGreaterThanOrEqual(2);
    await page2.close();
  });

  test("client sends heartbeat ping every 30 s and receives pong", async ({
    page,
  }) => {
    // Use fake timers in the page to advance 30 s without waiting
    const { waitForFrame } = collectWsFrames(page);
    await page.goto("/post/abc123");
    await page.waitForSelector("[data-ws-status='connected']");

    // Advance client-side timer
    await page.clock.fastForward(30_000);

    const ping = await waitForFrame(
      (f) => f.direction === "sent" && f.payload === "ping",
      3_000
    );
    expect(ping.payload).toBe("ping");

    const pong = await waitForFrame(
      (f) => f.direction === "received" && f.payload === "pong",
      3_000
    );
    expect(pong.payload).toBe("pong");
  });
});
```

## Assertions

Assert both the DOM update and the underlying protocol frame to catch regressions at both layers:

```typescript
test("DOM vote counter matches WebSocket payload", async ({ page, context }) => {
  const { waitForFrame } = collectWsFrames(page);

  await page.goto("/post/abc123");
  const counterLocator = page.locator("[data-testid='vote-count']");
  const initialCount = Number(await counterLocator.textContent());

  const page2 = await context.newPage();
  await page2.goto("/post/abc123");
  await page2.locator("[data-testid='upvote-btn']").click();

  const frame = await waitForFrame(
    (f) =>
      f.direction === "received" &&
      JSON.parse(f.payload).type === "vote_update"
  );
  const expected = JSON.parse(frame.payload).totalVotes;

  await expect(counterLocator).toHaveText(String(expected));
  expect(expected).toBe(initialCount + 1);
  await page2.close();
});
```

## CI Integration

```yaml
# .github/workflows/e2e.yml
name: E2E Tests
on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Install Playwright browsers
        run: pnpm playwright install --with-deps chromium
      - name: Run E2E
        run: pnpm playwright test e2e/realtime-votes.test.ts
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
          retention-days: 7
```

## Anti-patterns

- Polling the DOM for vote count updates with `page.waitForFunction` — this races against network and obscures whether the WS message actually arrived.
- Injecting a mock WebSocket in `page.addInitScript` — tests the mock, not the real Worker endpoint.
- Depending on `ws.on("close")` to detect test completion — a WS close is a side-effect, not a test signal; use `waitForFrame` with a predicate.
- Opening multiple browser contexts in the same test without closing them — leaves ghost connections that inflate presence counts in later tests.
- Using `page.waitForTimeout` to pause for WS messages — inherently flaky; always use event-driven waiting.

## Gotchas

- `page.on("websocket", ...)` must be registered before `page.goto` — frames emitted during page load are missed otherwise.
- Durable Object WebSocket Hibernation serialises messages through object storage; messages may arrive slightly out-of-order under load — assert on content, not sequence position.
- `page.clock.fastForward` only advances the browser clock, not the Worker clock; heartbeat tests assume the Worker accepts a `ping` at any time.
- Worker WebSocket upgrades require the `Upgrade: websocket` header; if `wrangler dev` is behind a proxy in CI, ensure the proxy passes the header through.
- Playwright traces record WS frames; enable `trace: "on"` when debugging frame content.

## Verification

```bash
pnpm playwright test e2e/realtime-votes.test.ts --headed
# Observe vote counts incrementing in real time across two browser windows.

pnpm playwright show-report
# Inspect WS frame timeline in the trace viewer.
```

## Related

- [playwright-workers-websocket-durable-objects-e2e.md](playwright-workers-websocket-durable-objects-e2e.md)
- [durable-objects-websocket-hibernation-testing.md](durable-objects-websocket-hibernation-testing.md)
- [websocket-realtime-testing.md](websocket-realtime-testing.md)
- [playwright-network-interception.md](playwright-network-interception.md)

## Sources

- https://playwright.dev/docs/api/class-websocket
- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://developers.cloudflare.com/workers/testing/local-development/
- https://playwright.dev/docs/clock
