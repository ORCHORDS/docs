# Vitest Workers TCP Socket connect() Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker uses `connect()` from `cloudflare:sockets` to open a raw TCP connection — typically to a database (PostgreSQL, MySQL, Redis) or an SMTP server — and you need unit and integration tests that verify the connection handshake logic, error handling, and read/write framing without spinning up a real TCP server in every CI run. Mocking the `connect()` import directly lets you assert on the socket API surface while keeping tests fast and hermetic.

## Context

`cloudflare:sockets` exposes a `connect(address, options?)` function that returns a `Socket` object with `.readable` (ReadableStream), `.writable` (WritableStream), `.startTls()`, and `.close()`. Workers using raw TCP are most commonly wrapping a database driver that calls `connect()` internally (e.g. `@neondatabase/serverless`, `@electric-sql/pglite-wasm`). For integration tests that require a real database, Hyperdrive or a local TCP server (via `wrangler dev`'s outbound tunnel) is the recommended approach; for unit tests of the Worker's own TCP-handling code, injecting a mock socket is cleaner.

## Configuring the Workers pool for cloudflare:sockets

```toml
# wrangler.toml
name = "tcp-worker"
main = "src/index.ts"
compatibility_date = "2025-06-01"
compatibility_flags = ["nodejs_compat"]

# No special binding needed — cloudflare:sockets is a built-in module
```

```ts
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

## Worker: wrapping connect() with a thin client

```ts
// src/tcp-client.ts
import { connect } from "cloudflare:sockets";

export interface TcpSocket {
  readable: ReadableStream<Uint8Array>;
  writable: WritableStream<Uint8Array>;
  startTls(): Promise<TcpSocket>;
  close(): Promise<void>;
}

export type ConnectFn = typeof connect;

export async function sendCommand(
  host: string,
  port: number,
  command: Uint8Array,
  connectFn: ConnectFn = connect
): Promise<Uint8Array> {
  const socket = connectFn({ hostname: host, port });

  const writer = socket.writable.getWriter();
  await writer.write(command);
  await writer.close();

  const reader = socket.readable.getReader();
  const chunks: Uint8Array[] = [];

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    chunks.push(value);
  }

  const total = chunks.reduce((n, c) => n + c.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  return result;
}
```

## Unit test: mocking connect() with a fake socket

```ts
// src/tcp-client.test.ts
import { describe, it, expect, vi } from "vitest";
import { sendCommand, type ConnectFn } from "./tcp-client";

function makeFakeSocket(response: Uint8Array) {
  let writerResolved = false;

  const readable = new ReadableStream<Uint8Array>({
    start(controller) {
      // Emit the response after the writer closes (simulates server reply)
      Promise.resolve().then(() => {
        if (writerResolved) {
          controller.enqueue(response);
          controller.close();
        }
      });
    },
  });

  const writable = new WritableStream<Uint8Array>({
    close() {
      writerResolved = true;
    },
  });

  return { readable, writable, startTls: async () => { throw new Error("unexpected"); }, close: async () => {} };
}

describe("sendCommand", () => {
  it("writes the command and returns the server response", async () => {
    const fakeResponse = new TextEncoder().encode("+PONG\r\n");
    const mockConnect = vi.fn().mockReturnValue(makeFakeSocket(fakeResponse)) as unknown as ConnectFn;

    const cmd = new TextEncoder().encode("*1\r\n$4\r\nPING\r\n");
    const result = await sendCommand("localhost", 6379, cmd, mockConnect);

    expect(mockConnect).toHaveBeenCalledWith({ hostname: "localhost", port: 6379 });
    expect(new TextDecoder().decode(result)).toBe("+PONG\r\n");
  });

  it("propagates connect errors as thrown exceptions", async () => {
    const mockConnect = vi.fn().mockImplementation(() => {
      const socket = makeFakeSocket(new Uint8Array());
      // Simulate connection refused via a broken readable
      const broken = new ReadableStream({ start(c) { c.error(new Error("ECONNREFUSED")); } });
      return { ...socket, readable: broken };
    }) as unknown as ConnectFn;

    await expect(
      sendCommand("localhost", 6379, new TextEncoder().encode("PING"), mockConnect)
    ).rejects.toThrow("ECONNREFUSED");
  });
});
```

## Integration test: connecting to wrangler dev's outbound tunnel

```ts
// src/tcp-integration.test.ts
// Run only when INTEGRATION=true to avoid requiring a live TCP server in unit CI
import { describe, it, expect } from "vitest";
import { sendCommand } from "./tcp-client";

const RUN_INTEGRATION = __ENV?.INTEGRATION === "true";

describe.skipIf(!RUN_INTEGRATION)("sendCommand — live TCP", () => {
  it("receives PONG from a local Redis on port 6379", async () => {
    const ping = new TextEncoder().encode("*1\r\n$4\r\nPING\r\n");
    const response = await sendCommand("127.0.0.1", 6379, ping);
    expect(new TextDecoder().decode(response)).toBe("+PONG\r\n");
  });
});
```

## Testing TLS upgrade via startTls()

```ts
// src/tls-upgrade.test.ts
import { it, expect, vi } from "vitest";
import { connect } from "cloudflare:sockets";

it("startTls() is called when the server signals STARTTLS", async () => {
  // Many protocols (SMTP, PostgreSQL) use STARTTLS: the client sends a command,
  // the server replies, and then the socket is upgraded.
  const startTls = vi.fn().mockImplementation(async () => ({
    readable: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode("220 TLS ok\r\n")); c.close(); } }),
    writable: new WritableStream(),
    startTls: vi.fn(),
    close: vi.fn(),
  }));

  const plainSocket = {
    readable: new ReadableStream({
      start(c) {
        // Server greets with "220 Ready to start TLS"
        c.enqueue(new TextEncoder().encode("220 Ready\r\n"));
        c.close();
      },
    }),
    writable: new WritableStream(),
    startTls,
    close: vi.fn(),
  };

  const mockConnect = vi.fn().mockReturnValue(plainSocket);

  // Call the function under test (your STARTTLS negotiation logic)
  const { negotiateTls } = await import("./tls-negotiator");
  await negotiateTls("smtp.example.com", 587, mockConnect as unknown as typeof connect);

  expect(startTls).toHaveBeenCalledOnce();
});
```

## Anti-patterns

- **Calling the real `connect()` in unit tests** — this requires a live TCP server and makes the suite non-hermetic. Inject `connectFn` as a parameter instead.
- **Mocking at the module level with `vi.mock('cloudflare:sockets')`** — the vitest-pool-workers environment resolves `cloudflare:sockets` as a Workers built-in; module-level mocking can conflict with the pool's module graph. Prefer dependency injection.
- **Forgetting to close the writer before reading** — many simple TCP protocols (Redis, SMTP commands) are half-duplex: the server only sends a response after the client closes the write side. Tests that read before closing will hang.
- **Testing the database driver's internals** — the driver (`postgres.js`, `mysql2`) already has its own tests. Test your Worker's logic that uses the driver's public API, not the driver's wire-protocol framing.

## Gotchas

- `connect()` from `cloudflare:sockets` is only available in the Workers runtime, not in Node.js. Tests run via `@cloudflare/vitest-pool-workers` have it; `vitest` running in the default Node pool does not.
- The `Socket` returned by `connect()` is a `TransformStream`-like object. `socket.readable` and `socket.writable` share backpressure: if nothing reads from `readable`, writes to `writable` will stall once internal buffers fill.
- `connect()` does not throw synchronously on connection refusal; it returns a socket whose `readable` becomes errored. Wrap `reader.read()` in a try/catch to handle the error case.
- The `allowHalfOpen` socket option (keep the readable open after the writer closes) is disabled by default. Some database protocols require it; pass `{ allowHalfOpen: true }` to `connect()` if the server sends data after the client write stream closes.

## Verification

```bash
# Unit tests only (no live server needed)
npx vitest run src/tcp-client.test.ts

# Integration tests (requires local Redis)
docker run -d -p 6379:6379 redis:7-alpine
INTEGRATION=true npx vitest run src/tcp-integration.test.ts
```

Expected: unit tests pass without any network calls; integration test logs `+PONG\r\n` and passes.

## Related

- `hyperdrive-connection-pool-testing-workers.md`
- `vitest-cloudflare-pool-workers.md`
- `miniflare-d1-integration-testing.md`
- `workers-test-patterns.md`

## Sources

- Cloudflare Docs — `cloudflare:sockets` (`connect()`): https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/
- Cloudflare Docs — Hyperdrive (TCP connection pooling): https://developers.cloudflare.com/hyperdrive/
- Vitest Docs — Dependency injection for testability: https://vitest.dev/guide/mocking#dependency-injection
- WHATWG Streams — `ReadableStream` error propagation: https://streams.spec.whatwg.org/#readablestream-set-up
