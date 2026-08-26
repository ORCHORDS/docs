# Vitest Workers: Request Clone and Stream Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your middleware reads `request.json()` or pipes `request.body` before forwarding
the request to the next handler. In tests the downstream handler receives a
`Request` whose body stream has already been consumed, so `request.json()`
throws `TypeError: body already used`. Alternatively, you are testing a
streaming upload handler and cannot figure out how to supply a
`ReadableStream` body that your Worker can read incrementally.

---

## Context

In the Workers runtime `Request` bodies are `ReadableStream`s — single-read by
the WHATWG Streams specification. Unlike Node.js `Buffer`-backed bodies, once
a stream has been read (via `.json()`, `.text()`, `.arrayBuffer()`, `.body
.getReader()`, or piped through `tee()`) the stream is locked and a second read
throws. The only safe way to share a body across consumers is `request.clone()`
(which creates a tee internally) or to buffer the body into memory first.

`vitest-pool-workers` runs tests inside a real Workers runtime via Miniflare,
so the exact same constraints apply in tests.

---

## 1. Why `request.clone()` Exists and How It Works

```typescript
// src/middleware/logger.ts

export async function loggingMiddleware(
  request: Request,
  next: (req: Request) => Promise<Response>
): Promise<Response> {
  // WRONG — consumes the body before next() can read it
  const body = await request.json();
  console.log("[logger] body:", body);
  return next(request); // ← body already used, will throw in handler

  // CORRECT — clone before reading
  const clone = request.clone();
  const body2 = await clone.json();
  console.log("[logger] body:", body2);
  return next(request); // original body still available
}
```

---

## 2. Testing Clone Behaviour in vitest-pool-workers

```typescript
// tests/middleware/logger.test.ts
import { describe, it, expect } from "vitest";
import { loggingMiddleware } from "../../src/middleware/logger.js";

describe("loggingMiddleware", () => {
  it("passes the original request body to the next handler", async () => {
    const payload = { action: "create", name: "Alice" };

    const request = new Request("https://example.com/api", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });

    let receivedBody: unknown;

    const response = await loggingMiddleware(request, async (req) => {
      receivedBody = await req.json(); // must NOT throw
      return new Response("ok");
    });

    expect(response.status).toBe(200);
    expect(receivedBody).toEqual(payload);
  });

  it("does not consume the original stream when logging", async () => {
    const request = new Request("https://example.com/api", {
      method: "PUT",
      body: "hello stream",
    });

    // Body locked state before handler runs
    expect(request.bodyUsed).toBe(false);

    await loggingMiddleware(request, async (req) => {
      expect(req.bodyUsed).toBe(false); // original must still be readable
      return new Response(await req.text());
    });
  });
});
```

---

## 3. Supplying a ReadableStream Body in Tests

```typescript
// tests/helpers/stream.ts
export function stringToStream(text: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
}

export function chunkedStream(
  chunks: string[],
  delayMs = 0
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      for (const chunk of chunks) {
        if (delayMs > 0) {
          await new Promise((r) => setTimeout(r, delayMs));
        }
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}
```

```typescript
// tests/handlers/upload.test.ts
import { describe, it, expect } from "vitest";
import { handleUpload } from "../../src/handlers/upload.js";
import { chunkedStream } from "../helpers/stream.js";

describe("streaming upload handler", () => {
  it("reads a chunked NDJSON stream and persists each line", async () => {
    const ndjson = ['{"id":1,"val":"a"}', '{"id":2,"val":"b"}', ""].join("\n");

    const request = new Request("https://example.com/upload", {
      method: "POST",
      headers: { "content-type": "application/x-ndjson" },
      // Supply as a real ReadableStream — not a pre-buffered string
      body: chunkedStream(ndjson.split("\n").map((l) => l + "\n")),
      // duplex is required when body is a ReadableStream in some environments
      // @ts-expect-error — not in the Workers types but required for streaming
      duplex: "half",
    });

    const env = { DB: {} }; // minimal binding stub
    const ctx = { waitUntil: () => {}, passThroughOnException: () => {} };

    const response = await handleUpload(request, env as never, ctx as never);
    expect(response.status).toBe(200);

    const result = await response.json<{ inserted: number }>();
    expect(result.inserted).toBe(2);
  });
});
```

---

## 4. Testing a `request.body.tee()` Pattern

```typescript
// src/handlers/audit-proxy.ts
export async function auditProxy(
  request: Request,
  env: { AUDIT_LOG: Queue }
): Promise<Response> {
  // tee the body so we can audit it AND forward it
  const [forAudit, forUpstream] = request.body!.tee();

  // Fire-and-forget audit log
  const auditReq = new Request(request.url, {
    method: request.method,
    headers: request.headers,
    body: forAudit,
  });
  env.AUDIT_LOG.send({ body: await auditReq.text() }).catch(console.error);

  // Forward original body
  return fetch(new Request(request.url, {
    method: request.method,
    headers: request.headers,
    body: forUpstream,
  }));
}
```

```typescript
// tests/handlers/audit-proxy.test.ts
import { describe, it, expect, vi } from "vitest";
import { auditProxy } from "../../src/handlers/audit-proxy.js";

describe("auditProxy tee behaviour", () => {
  it("sends audit message AND forwards the full body", async () => {
    const sentMessages: unknown[] = [];
    const mockQueue = { send: vi.fn((msg) => { sentMessages.push(msg); return Promise.resolve(); }) };

    // Mock upstream fetch
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("upstream ok", { status: 200 })
    );

    const request = new Request("https://api.example.com/data", {
      method: "POST",
      body: JSON.stringify({ user: "alice" }),
    });

    const response = await auditProxy(request, { AUDIT_LOG: mockQueue as never });

    expect(response.status).toBe(200);
    expect(mockQueue.send).toHaveBeenCalledOnce();
    expect(sentMessages[0]).toMatchObject({ body: expect.stringContaining("alice") });

    // Verify the body forwarded to upstream was not empty
    const forwardedBody = await fetchSpy.mock.calls[0][0].text();
    expect(forwardedBody).toContain("alice");

    fetchSpy.mockRestore();
  });
});
```

---

## 5. Asserting `bodyUsed` State Transitions

```typescript
// tests/stream-state.test.ts
import { describe, it, expect } from "vitest";

describe("Request bodyUsed state machine", () => {
  it("marks bodyUsed after .json()", async () => {
    const req = new Request("https://x.com", {
      method: "POST",
      body: "{}",
    });
    expect(req.bodyUsed).toBe(false);
    await req.json();
    expect(req.bodyUsed).toBe(true);
  });

  it("clone() produces an independent stream", async () => {
    const req = new Request("https://x.com", {
      method: "POST",
      body: '{"x":1}',
    });
    const clone = req.clone();

    // Consume clone
    const fromClone = await clone.json<{ x: number }>();
    expect(fromClone.x).toBe(1);
    expect(clone.bodyUsed).toBe(true);

    // Original still readable
    expect(req.bodyUsed).toBe(false);
    const fromOrig = await req.json<{ x: number }>();
    expect(fromOrig.x).toBe(1);
  });

  it("throws on double-read without clone", async () => {
    const req = new Request("https://x.com", { method: "POST", body: "hi" });
    await req.text();
    await expect(req.text()).rejects.toThrow(/body (already used|locked)/i);
  });
});
```

---

## 6. Vitest Config for Pool Workers

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "wrangler.toml" },
        miniflare: {
          compatibilityDate: "2025-01-01",
          compatibilityFlags: ["nodejs_compat"],
        },
      },
    },
  },
});
```

---

## Anti-patterns

- **Using `Buffer.from(await request.arrayBuffer())` to "reset" a body** –
  This consumes the stream. If you need to pass the body downstream, clone
  before any read.
- **Supplying a plain `string` when you want to test chunking** – A `string`
  body is buffered into a single chunk. Use `ReadableStream` helpers (section 3)
  for chunked-arrival semantics.
- **Checking `request.body === null`** – A GET/HEAD request has `body: null`.
  Calling `.clone()` on such a request still works; the cloned body is also
  `null`. Guard with `request.body !== null` before calling `.tee()`.
- **Leaking reader locks** – If you call `request.body.getReader()` and never
  `release()` it, the stream remains locked for the rest of the request
  lifetime. Always use `try/finally` to release.

---

## Gotchas

- `request.clone()` after any partial read (even `getReader()` without reading)
  throws `TypeError: Cannot clone a Request with a locked body`.
- The `duplex: "half"` option is required in some fetch implementations when
  supplying a `ReadableStream` body; Workers types don't expose it but the
  runtime accepts it.
- Miniflare uses the `undici` WHATWG Fetch implementation under the hood in
  non-pool-workers mode. Stream semantics are slightly different from the
  production Workers runtime; prefer `vitest-pool-workers` for stream tests.
- In the Workers runtime, streaming response bodies from `fetch()` are also
  single-read. If you need to inspect and forward, `tee()` the response body
  too.

---

## Verification

```bash
# Run only stream-related tests
vitest run --reporter=verbose tests/stream-state.test.ts tests/handlers/upload.test.ts

# Confirm pool-workers config picks up wrangler.toml
vitest run --config vitest.config.ts --pool=workers
```

---

## Related

- `vitest-pool-workers-cloudflare-test-api.md`
- `vitest-workers-miniflare-testing-setup.md`
- `vitest-workers-queue-batch-testing.md`
- `vitest-workers-module-mock-inject.md`
- `hono-test-utils-workers-unit-testing.md`

---

## Sources

- WHATWG Streams specification: https://streams.spec.whatwg.org/
- Cloudflare Workers Streams API: https://developers.cloudflare.com/workers/runtime-apis/streams/
- `@cloudflare/vitest-pool-workers` docs: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Miniflare fetch implementation: https://github.com/cloudflare/miniflare
