# Vitest Workers WebSocket Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Cloudflare Worker handles WebSocket upgrades via the `WebSocketPair` API and you need reliable
unit tests that exercise the full handshake, message exchange, and close sequences without hitting
a live network.

## Context
Cloudflare Workers uses a non-standard `WebSocketPair` + `Response(null, { webSocket })` pattern
rather than the Node.js `ws` library. Miniflare v3/v4 ships with a built-in WebSocket implementation
that mirrors the runtime, letting `@cloudflare/vitest-pool-workers` run these tests inside the same
Workers environment. Tests run as a real Worker, so the `WebSocket` global is the Cloudflare variant,
not the browser or Node.js one.

## Setting Up the Test Environment

Install the pool and configure Vitest to use it:

```bash
pnpm add -D @cloudflare/vitest-pool-workers vitest
```

```ts
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          compatibilityDate: "2024-09-23",
          compatibilityFlags: ["nodejs_compat"],
        },
      },
    },
  },
});
```

## Writing the Worker Under Test

```ts
// src/index.ts
export default {
  async fetch(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get("Upgrade");
    if (upgradeHeader !== "websocket") {
      return new Response("Expected WebSocket upgrade", { status: 426 });
    }

    const [client, server] = Object.values(new WebSocketPair());

    server.accept();

    server.addEventListener("message", (event) => {
      const msg = event.data as string;
      if (msg === "ping") {
        server.send("pong");
      } else {
        server.send(`echo: ${msg}`);
      }
    });

    server.addEventListener("close", () => {
      server.close(1000, "Goodbye");
    });

    return new Response(null, {
      status: 101,
      webSocket: client,
    });
  },
} satisfies ExportedHandler;
```

## Testing Handshake and Message Exchange

```ts
// src/index.test.ts
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import worker from "./index";

describe("WebSocket handler", () => {
  it("rejects non-WebSocket requests", async () => {
    const req = new Request("http://localhost/ws");
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);
    expect(res.status).toBe(426);
  });

  it("upgrades the connection on a proper WebSocket request", async () => {
    const req = new Request("http://localhost/ws", {
      headers: { Upgrade: "websocket" },
    });
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(101);
    // The response carries the client-side socket
    expect(res.webSocket).not.toBeNull();
  });

  it("responds to ping with pong", async () => {
    const req = new Request("http://localhost/ws", {
      headers: { Upgrade: "websocket" },
    });
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    const ws = res.webSocket!;
    ws.accept(); // accept on the client side

    const received: string[] = [];
    ws.addEventListener("message", (e) => received.push(e.data as string));

    ws.send("ping");
    // Miniflare delivers messages synchronously within the microtask queue
    await new Promise((r) => setTimeout(r, 0));

    expect(received).toContain("pong");
  });

  it("echoes arbitrary messages", async () => {
    const req = new Request("http://localhost/ws", {
      headers: { Upgrade: "websocket" },
    });
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    const ws = res.webSocket!;
    ws.accept();

    const messages: string[] = [];
    ws.addEventListener("message", (e) => messages.push(e.data as string));

    ws.send("hello");
    await new Promise((r) => setTimeout(r, 0));

    expect(messages[0]).toBe("echo: hello");
  });
});
```

## Testing Close Sequences

```ts
it("sends close frame and cleans up", async () => {
  const req = new Request("http://localhost/ws", {
    headers: { Upgrade: "websocket" },
  });
  const ctx = createExecutionContext();
  const res = await worker.fetch(req, env, ctx);
  await waitOnExecutionContext(ctx);

  const ws = res.webSocket!;
  ws.accept();

  let closedCode: number | undefined;
  ws.addEventListener("close", (e) => {
    closedCode = e.code;
  });

  ws.close(1000, "done");
  await new Promise((r) => setTimeout(r, 0));

  // Server re-echoes the close with code 1000
  expect(closedCode).toBe(1000);
});
```

## Anti-patterns
- Do not use the Node.js `ws` package in tests — it creates real TCP sockets and bypasses the
  Workers runtime, making test behaviour diverge from production.
- Do not forget to call `ws.accept()` on the client socket in the test; without it, the socket
  stays in the `CONNECTING` state and messages are queued indefinitely.
- Do not use `setTimeout` with arbitrary large delays to wait for messages; prefer a `Promise`
  resolved inside the event listener to avoid flakiness.
- Do not test Durable Object WebSockets with this pattern alone; DO hibernation requires
  `ctx.acceptWebSocket()` and a separate test strategy.

## Gotchas
- `res.webSocket` is a Cloudflare-only extension on `Response`; TypeScript needs
  `@cloudflare/workers-types` in scope or the property will not type-check.
- Messages sent before `ws.accept()` are buffered, not dropped, which can mask ordering bugs.
- The `WebSocketPair` constructor returns an object with numeric keys (`0`, `1`);
  `Object.values(new WebSocketPair())` is the idiomatic way to destructure in TypeScript.
- Miniflare's in-process message delivery is synchronous after a single microtask tick; real
  production latency is higher, so do not rely on ordering guarantees between turns.

## Verification

```bash
# Run only WebSocket tests
pnpm vitest run --reporter=verbose src/index.test.ts

# Watch mode during development
pnpm vitest --reporter=verbose src/index.test.ts
```

## Related
- `miniflare-durable-objects-fake-clock-testing.md` — DO alarm + hibernation testing
- `vitest-workers-queue-batch-testing.md` — Queue consumer test patterns
- `vitest-pool-workers-cloudflare-test-api.md` — `cloudflare:test` module API reference
- `wrangler-dev-inspector-websocket-protocol.md` — Inspector protocol for live debugging

## Sources
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/workers/runtime-apis/websockets/
- https://miniflare.dev/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
