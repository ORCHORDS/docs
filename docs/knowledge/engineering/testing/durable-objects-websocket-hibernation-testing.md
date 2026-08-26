# Durable Objects WebSocket Hibernation Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Durable Objects that use the WebSocket Hibernation API (`this.state.acceptWebSocket()`) behave differently from plain WebSocket servers because the DO can be evicted between messages. Testing these DOs requires exercising the `webSocketMessage`, `webSocketClose`, and `webSocketError` handlers independently of an actual connection lifecycle.

## Context
The WebSocket Hibernation API lets a DO accept a WebSocket, go dormant, and be re-hydrated when the next message arrives. The runtime calls `webSocketMessage(ws, message)` on a fresh DO instance. Miniflare 3 supports calling these handlers directly through `runInDurableObject`, enabling precise per-handler unit tests without needing a live WebSocket upgrade. The `@cloudflare/vitest-pool-workers` pool exposes the helpers required to drive the DO and inspect its storage.

## Implementing the Hibernating DO

```typescript
// src/chat-room.ts
export class ChatRoomDO implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }
    const [client, server] = Object.values(new WebSocketPair());
    this.state.acceptWebSocket(server, ["chat"]);
    await this.state.storage.put("connectionCount", (await this.state.storage.get<number>("connectionCount") ?? 0) + 1);
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const text = typeof message === "string" ? message : new TextDecoder().decode(message);
    const parsed = JSON.parse(text) as { type: string; payload: unknown };
    if (parsed.type === "ping") {
      ws.send(JSON.stringify({ type: "pong", ts: Date.now() }));
    } else if (parsed.type === "broadcast") {
      for (const peer of this.state.getWebSockets("chat")) {
        if (peer !== ws) peer.send(JSON.stringify({ type: "message", data: parsed.payload }));
      }
    }
    await this.state.storage.put("lastMessage", text);
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    await this.state.storage.put("lastClose", { code, reason });
    ws.close(code, "Server closing");
  }

  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    await this.state.storage.put("lastError", String(error));
  }
}
```

## Testing webSocketMessage Handler

Call the handler directly via `runInDurableObject` without a real WebSocket connection:

```typescript
// tests/chat-room.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { env, runInDurableObject } from "cloudflare:test";

function makeFakeWS(): WebSocket & { sent: string[] } {
  const sent: string[] = [];
  return Object.assign(
    { send: (msg: string) => { sent.push(msg); }, close: () => {} } as unknown as WebSocket,
    { sent }
  );
}

describe("ChatRoomDO webSocketMessage", () => {
  let stub: ReturnType<DurableObjectNamespace["get"]>;

  beforeEach(() => {
    stub = env.CHAT_ROOM.get(env.CHAT_ROOM.idFromName("room-1"));
  });

  it("replies with pong on ping message", async () => {
    const ws = makeFakeWS();
    await runInDurableObject(stub, async (instance) => {
      await (instance as ChatRoomDO).webSocketMessage(ws, JSON.stringify({ type: "ping" }));
    });
    expect(ws.sent).toHaveLength(1);
    expect(JSON.parse(ws.sent[0])).toMatchObject({ type: "pong" });
  });

  it("stores last message text in storage", async () => {
    const ws = makeFakeWS();
    const msg = JSON.stringify({ type: "ping" });
    await runInDurableObject(stub, async (instance, state) => {
      await (instance as ChatRoomDO).webSocketMessage(ws, msg);
      expect(await state.storage.get<string>("lastMessage")).toBe(msg);
    });
  });
});
```

## Testing webSocketClose Handler

```typescript
// tests/chat-room-close.test.ts
import { it, expect } from "vitest";
import { env, runInDurableObject } from "cloudflare:test";

it("records close code and reason in storage", async () => {
  const stub = env.CHAT_ROOM.get(env.CHAT_ROOM.idFromName("room-close"));
  const ws = {
    close: (code: number, reason: string) => {},
  } as unknown as WebSocket;

  await runInDurableObject(stub, async (instance, state) => {
    await (instance as unknown as { webSocketClose: Function }).webSocketClose(ws, 1001, "going away");
    const stored = await state.storage.get<{ code: number; reason: string }>("lastClose");
    expect(stored?.code).toBe(1001);
    expect(stored?.reason).toBe("going away");
  });
});
```

## Testing Connection Count via fetch()

Test the `fetch` path that upgrades the connection and increments a counter, using a synthetic WebSocket upgrade request:

```typescript
// tests/chat-room-connect.test.ts
import { it, expect } from "vitest";
import { env, runInDurableObject, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";

it("increments connectionCount on each upgrade", async () => {
  const stub = env.CHAT_ROOM.get(env.CHAT_ROOM.idFromName("room-count"));

  const upgradeRequest = new Request("https://chat.example.com/", {
    headers: { Upgrade: "websocket" },
  });

  // First connection
  const ctx1 = createExecutionContext();
  const res1 = await stub.fetch(upgradeRequest, ctx1);
  await waitOnExecutionContext(ctx1);
  expect(res1.status).toBe(101);

  // Second connection — same DO instance, count should be 2
  const ctx2 = createExecutionContext();
  await stub.fetch(upgradeRequest, ctx2);
  await waitOnExecutionContext(ctx2);

  await runInDurableObject(stub, async (_i, state) => {
    expect(await state.storage.get<number>("connectionCount")).toBe(2);
  });
});
```

## Testing webSocketError Handler

```typescript
// tests/chat-room-error.test.ts
import { it, expect } from "vitest";
import { env, runInDurableObject } from "cloudflare:test";

it("stores error message in storage", async () => {
  const stub = env.CHAT_ROOM.get(env.CHAT_ROOM.idFromName("room-err"));
  const fakeWs = {} as WebSocket;
  const error = new Error("connection reset");

  await runInDurableObject(stub, async (instance, state) => {
    await (instance as unknown as { webSocketError: Function }).webSocketError(fakeWs, error);
    expect(await state.storage.get<string>("lastError")).toContain("connection reset");
  });
});
```

## Anti-patterns
- Do not create a real `WebSocket` client in unit tests — `new WebSocket()` is not available in the Miniflare worker environment without a running server.
- Avoid testing broadcast logic by asserting `ws.sent` on the sender; iterate `state.getWebSockets()` or check storage side-effects instead.
- Do not reuse the same DO id across tests that check connection counts; isolation requires fresh names per test.

## Gotchas
- `state.getWebSockets()` returns an empty array in `runInDurableObject` because no real WebSocket handshake occurred; test broadcast by hooking `peer.send` spies before calling the handler.
- Miniflare does not enforce the 1 MB message size limit on WebSocket messages — production will reject oversized frames silently.
- When a hibernated DO is re-hydrated, its in-memory state is lost; verify that your handler only reads from `state.storage`, not from class fields set in a prior invocation.
- Tags passed to `acceptWebSocket(ws, tags)` are preserved across hibernation; test tag-filtered sends with `state.getWebSockets("tag")`.

## Verification
`npx vitest run tests/chat-room.test.ts` — all tests should complete without network activity. Use `--reporter=verbose` to confirm each handler path is reached.

## Related
- [durable-objects-miniflare-fake-timers.md](durable-objects-miniflare-fake-timers.md)
- [durable-objects-alarm-testing-miniflare.md](durable-objects-alarm-testing-miniflare.md)
- [websocket-realtime-testing.md](websocket-realtime-testing.md)
- [vitest-cloudflare-pool-workers.md](vitest-cloudflare-pool-workers.md)

## Sources
- https://developers.cloudflare.com/durable-objects/reference/websockets/
- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
