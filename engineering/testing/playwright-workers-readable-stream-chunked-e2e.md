# Playwright Workers ReadableStream Chunked Response E2E

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker returns a `ReadableStream` — a chunked JSON-LD feed, a server-sent binary blob, or a streamed AI completion not using the SSE event format — and you need to assert on the *stream itself*: that chunks arrive incrementally, that the final concatenated body is correct, and that the client-side rendering that depends on progressive delivery works as expected. Standard Playwright `response.json()` awaits the full body and can't observe chunk timing or ordering.

## Context

Cloudflare Workers can return `ReadableStream` bodies with `Transfer-Encoding: chunked` behaviour. Unlike SSE (which uses `text/event-stream` and a well-known parsing protocol), raw streams carry arbitrary chunk boundaries. E2E testing these requires intercepting responses at the network level, reading the stream incrementally, and correlating chunk arrival with DOM updates. Playwright's `page.route` + `request.fetchResponse()` combined with `ReadableStreamDefaultReader` gives you the chunk-level view without a custom proxy.

## Worker: streaming chunked JSON fragments

```ts
// src/index.ts
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const count = parseInt(url.searchParams.get("n") ?? "5", 10);

    const stream = new ReadableStream({
      async start(controller) {
        for (let i = 0; i < count; i++) {
          const chunk = JSON.stringify({ index: i, value: i * i }) + "\n";
          controller.enqueue(new TextEncoder().encode(chunk));
          // Simulate processing delay between chunks
          await new Promise((r) => setTimeout(r, 50));
        }
        controller.close();
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "application/x-ndjson",
        "X-Chunk-Count": String(count),
      },
    });
  },
} satisfies ExportedHandler;
```

## Playwright: intercepting the stream at the route level

```ts
// tests/stream.spec.ts
import { test, expect } from "@playwright/test";

test("worker delivers chunks incrementally", async ({ page }) => {
  const chunks: string[] = [];

  // Intercept the stream endpoint before navigating
  await page.route("**/stream**", async (route) => {
    const response = await route.fetch();
    const reader = response.body()!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      chunks.push(decoder.decode(value, { stream: true }));
    }

    // Let the browser see the full response as well
    await route.fulfill({ response });
  });

  await page.goto("/stream?n=4");

  // Assert at least 2 chunks were delivered (not one monolithic body)
  expect(chunks.length).toBeGreaterThanOrEqual(2);
});
```

## Playwright: asserting DOM updates as chunks arrive

```ts
// tests/progressive-render.spec.ts
import { test, expect } from "@playwright/test";

test("page renders items progressively as chunks arrive", async ({ page }) => {
  // The page uses fetch() + a ReadableStream reader to append rows
  await page.goto("/progressive-list?n=5");

  // First item should appear before the last item
  const firstItem = page.locator('[data-index="0"]');
  await expect(firstItem).toBeVisible({ timeout: 500 });

  // Full list only after all chunks are consumed
  const allItems = page.locator("[data-index]");
  await expect(allItems).toHaveCount(5, { timeout: 2000 });
});
```

## Playwright: asserting chunk content with accumulated decoding

```ts
// tests/ndjson-content.spec.ts
import { test, expect } from "@playwright/test";

test("each chunk is valid NDJSON and values are correct", async ({ page }) => {
  const lines: Array<{ index: number; value: number }> = [];
  const pending: string[] = [];

  await page.route("**/stream**", async (route) => {
    const response = await route.fetch();
    const reader = response.body()!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Split on newlines to handle chunks that carry partial lines
      const parts = buffer.split("\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        if (part.trim()) lines.push(JSON.parse(part));
      }
    }
    if (buffer.trim()) lines.push(JSON.parse(buffer));
    await route.fulfill({ response });
  });

  await page.goto("/stream?n=4");

  expect(lines).toHaveLength(4);
  for (const line of lines) {
    expect(line.value).toBe(line.index ** 2);
  }
});
```

## Playwright: measuring time-to-first-chunk

```ts
// tests/ttfc.spec.ts
import { test, expect } from "@playwright/test";

test("time-to-first-chunk is under 200 ms", async ({ page }) => {
  let firstChunkAt: number | null = null;
  const requestStart = Date.now();

  await page.route("**/stream**", async (route) => {
    const response = await route.fetch();
    const reader = response.body()!.getReader();

    const { done } = await reader.read();
    if (!done) firstChunkAt = Date.now();

    // Drain the rest
    while (!(await reader.read()).done) {/* noop */}

    await route.fulfill({ response });
  });

  await page.goto("/stream?n=3");

  expect(firstChunkAt).not.toBeNull();
  expect(firstChunkAt! - requestStart).toBeLessThan(200);
});
```

## Anti-patterns

- **Using `response.text()` or `response.json()` in route handlers** — these buffer the entire body and destroy chunk-level observability. Use `response.body()!.getReader()` instead.
- **Asserting `chunks.length === n`** — network and runtime buffering can merge adjacent chunks. Assert `>= 2` (not `=== n`) to verify streaming without coupling to buffer sizes.
- **Polling the DOM for count instead of awaiting the stream** — race conditions between the interceptor and DOM updates cause intermittent failures. Let `waitForResponse` or locator assertions drive synchronization.
- **Skipping the `{ stream: true }` flag in `TextDecoder.decode`** — without it, multi-byte characters split across chunks are decoded incorrectly; `stream: true` tells the decoder to hold incomplete sequences.

## Gotchas

- `route.fetch()` in Playwright returns a synthetic `APIResponse` whose `.body()` is a `ReadableStream`. This stream is the intercepted bytes — consuming it inside the route handler means you must call `route.fulfill({ response })` with the same `APIResponse` object, which replays the body for the browser. Do not call `response.body()` twice.
- If the Worker flushes chunks via `setTimeout`, the Playwright route's `await reader.read()` blocks until the runtime delivers the chunk; no polling is needed.
- Workers running behind `wrangler dev --remote` may buffer chunks at the edge; test against `wrangler dev` (local) to measure true streaming behaviour.
- `Transfer-Encoding: chunked` is an HTTP/1.1 concept. HTTP/2 uses DATA frames instead. Chunk boundaries in the `ReadableStream` reader reflect the runtime's framing, not the HTTP wire chunking, so chunk counts observed in tests may differ from curl output.

## Verification

```bash
# Confirm the Worker streams (should print multiple lines as they arrive)
curl -N http://localhost:8787/stream?n=4

# Run the Playwright suite
npx playwright test tests/stream.spec.ts tests/ndjson-content.spec.ts --reporter=list
```

Expected: curl prints lines with visible pauses between them; all Playwright assertions pass.

## Related

- `playwright-workers-sse-streaming-test.md`
- `streaming-sse-testing.md`
- `playwright-network-interception.md`
- `playwright-workers-api-contract-e2e-testing.md`

## Sources

- Playwright Docs — `page.route()` and `route.fetch()`: https://playwright.dev/docs/network#modify-responses
- Cloudflare Docs — ReadableStream in Workers: https://developers.cloudflare.com/workers/runtime-apis/streams/readablestream/
- WHATWG Streams spec — `ReadableStreamDefaultReader.read()`: https://streams.spec.whatwg.org/#default-reader-read
- MDN — `TextDecoder` `stream` option: https://developer.mozilla.org/en-US/docs/Web/API/TextDecoder/decode
