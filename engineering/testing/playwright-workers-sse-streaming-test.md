# Playwright Workers SSE Streaming Real-Time Test
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Worker returns a `text/event-stream` response that pushes real-time events to browser
clients (live dashboard, progress notifications, log tailing). You need an E2E test that:
1. Opens a browser tab that connects to the SSE endpoint.
2. Asserts that events arrive in the correct order within a time budget.
3. Verifies the client-side UI reacts to each event (DOM updates, counters, etc.).
4. Confirms the stream closes cleanly when the Worker signals `data: [DONE]`.

## Context
Server-Sent Events (SSE) over Cloudflare Workers use the Streams API: a `ReadableStream` is
returned directly in the `Response` constructor with `Content-Type: text/event-stream` and
`Cache-Control: no-cache`. Playwright can intercept the response body as a stream using
`page.on('response')` plus `response.body()`, or, more naturally, by scripting the browser's
built-in `EventSource` API via `page.evaluate`. The `EventSource` approach is preferred because it
exercises the same code path a real user's browser would follow.

## Project Layout
```
workers/
  src/
    sse-handler.ts    # SSE Worker
    index.ts
  wrangler.toml
e2e/
  sse-streaming.spec.ts
  helpers/
    sse-collector.ts  # captures EventSource events inside Playwright
playwright.config.ts
```

## Worker: SSE Endpoint
`workers/src/sse-handler.ts`:
```typescript
export interface Env {}

export function createSseStream(steps: string[], intervalMs = 100): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let idx = 0;

  return new ReadableStream({
    async pull(controller) {
      if (idx < steps.length) {
        const event = `id: ${idx}\ndata: ${JSON.stringify({ step: steps[idx], index: idx })}\n\n`;
        controller.enqueue(encoder.encode(event));
        idx++;
        // Simulate async work between events
        await new Promise((r) => setTimeout(r, intervalMs));
      } else {
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      }
    },
  });
}

export default {
  async fetch(req: Request, _env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/stream') {
      const steps = ['initialising', 'loading', 'processing', 'complete'];
      return new Response(createSseStream(steps), {
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Access-Control-Allow-Origin': '*',
        },
      });
    }

    // Serve a simple HTML page that renders SSE events into the DOM
    if (url.pathname === '/' || url.pathname === '/index.html') {
      return new Response(
        `<!DOCTYPE html><html><body>
          <ul id="events"></ul>
          <span id="status">connecting</span>
          <script>
            const es = new EventSource('/stream');
            const list = document.getElementById('events');
            const status = document.getElementById('status');
            status.textContent = 'connected';
            es.onmessage = (e) => {
              const data = JSON.parse(e.data);
              if (data === '[DONE]' || e.data === '[DONE]') {
                status.textContent = 'done';
                es.close();
                return;
              }
              const li = document.createElement('li');
              li.textContent = data.step;
              li.setAttribute('data-index', String(data.index));
              list.appendChild(li);
              status.textContent = data.step;
            };
            es.onerror = () => { status.textContent = 'error'; };
          </script>
        </body></html>`,
        { headers: { 'Content-Type': 'text/html' } },
      );
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Playwright Helper: SSE Collector
`e2e/helpers/sse-collector.ts`:
```typescript
import { Page } from '@playwright/test';

export interface SseEvent {
  lastEventId: string;
  data: string;
}

/**
 * Opens an EventSource from inside the browser and captures all messages
 * into a buffer on the window object.
 *
 * @param page  - Playwright Page
 * @param url   - SSE endpoint URL
 * @param key   - unique window key (prevents collisions when multiple streams
 *                are opened in the same test)
 */
export async function collectSse(
  page: Page,
  url: string,
  key = '_sse_collector',
): Promise<{
  waitForCount(n: number, timeout?: number): Promise<SseEvent[]>;
  waitForDone(timeout?: number): Promise<void>;
  events(): Promise<SseEvent[]>;
}> {
  await page.evaluate(
    ({ sseUrl, bufKey }: { sseUrl: string; bufKey: string }) => {
      const buf: SseEvent[] = [];
      let done = false;
      const es = new EventSource(sseUrl);
      es.onmessage = (e: MessageEvent) => {
        if (e.data === '[DONE]') { done = true; es.close(); return; }
        buf.push({ lastEventId: e.lastEventId, data: e.data });
      };
      (window as Record<string, unknown>)[bufKey] = { buf, isDone: () => done, es };
    },
    { sseUrl: url, bufKey: key },
  );

  return {
    async waitForCount(n: number, timeout = 10_000): Promise<SseEvent[]> {
      await page.waitForFunction(
        ({ k, count }: { k: string; count: number }) =>
          ((window as Record<string, unknown>)[k] as { buf: unknown[] }).buf.length >= count,
        { k: key, count: n },
        { timeout },
      );
      return page.evaluate(
        (k: string) => ((window as Record<string, unknown>)[k] as { buf: SseEvent[] }).buf.slice(),
        key,
      );
    },
    async waitForDone(timeout = 15_000): Promise<void> {
      await page.waitForFunction(
        (k: string) => ((window as Record<string, unknown>)[k] as { isDone(): boolean }).isDone(),
        key,
        { timeout },
      );
    },
    async events(): Promise<SseEvent[]> {
      return page.evaluate(
        (k: string) => ((window as Record<string, unknown>)[k] as { buf: SseEvent[] }).buf.slice(),
        key,
      );
    },
  };
}
```

## E2E Spec
`e2e/sse-streaming.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';
import { collectSse } from './helpers/sse-collector';

const BASE_URL = process.env.WORKER_URL ?? 'http://localhost:8787';

test.describe('SSE streaming Worker E2E', () => {
  test('receives all events in order and stream closes with [DONE]', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);

    // Wait for DOM to reflect each step
    await expect(page.locator('#status')).toHaveText('connected', { timeout: 3_000 });

    // All 4 steps arrive in the DOM
    await expect(page.locator('#events li')).toHaveCount(4, { timeout: 10_000 });

    // Verify order
    const texts = await page.locator('#events li').allTextContents();
    expect(texts).toEqual(['initialising', 'loading', 'processing', 'complete']);

    // Stream closed, status updated to 'done'
    await expect(page.locator('#status')).toHaveText('done', { timeout: 5_000 });
  });

  test('EventSource collector captures raw event data', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);

    const collector = await collectSse(page, `${BASE_URL}/stream`);
    const events = await collector.waitForCount(4);

    expect(events).toHaveLength(4);
    expect(JSON.parse(events[0].data)).toMatchObject({ step: 'initialising', index: 0 });
    expect(JSON.parse(events[3].data)).toMatchObject({ step: 'complete', index: 3 });

    await collector.waitForDone();
  });

  test('event IDs increment monotonically', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);

    const collector = await collectSse(page, `${BASE_URL}/stream`);
    const events = await collector.waitForCount(4);

    const ids = events.map((e) => parseInt(e.lastEventId));
    expect(ids).toEqual([0, 1, 2, 3]);
  });

  test('no error state on clean stream completion', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await expect(page.locator('#status')).not.toHaveText('error', { timeout: 10_000 });
    await expect(page.locator('#status')).toHaveText('done', { timeout: 10_000 });
  });
});
```

`playwright.config.ts` excerpt:
```typescript
export default defineConfig({
  testDir: './e2e',
  use: { baseURL: process.env.WORKER_URL ?? 'http://localhost:8787' },
  webServer: {
    command: 'wrangler dev --local --port 8787',
    url: 'http://localhost:8787',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
```

## Anti-patterns
- **Using `page.route` to intercept SSE** – Playwright's route interception buffers the entire
  response body before handing it to your handler, breaking streaming; always let the browser's
  native `EventSource` receive the stream.
- **Asserting on `response.body()` byte counts** – SSE frame boundaries are not aligned with TCP
  segments; byte-level assertions are inherently flaky. Assert on parsed event data instead.
- **`page.waitForResponse` on an SSE endpoint** – this resolves when headers arrive, not when the
  stream is complete. Use `waitForFunction` on a DOM mutation or buffered event count.
- **Not setting `Access-Control-Allow-Origin`** – if the page origin differs from the Worker origin
  (e.g. Pages frontend vs. Workers API), the `EventSource` request will be blocked by CORS.

## Gotchas
- `wrangler dev --local` respects the `ReadableStream` pull-based approach, but if you use
  `TransformStream` with a `WritableStream` producer, ensure you `await` the writer flush on each
  chunk or Miniflare may buffer until the entire stream is done.
- Playwright's `waitForFunction` polls at ~100 ms intervals by default; for very fast streams
  (< 10 ms between events) you may miss intermediate states. Capture the full buffer and assert on
  the final snapshot rather than individual transient states.
- Worker SSE does not support `retry:` field parsing in all versions of `wrangler dev`; if your
  client reconnection logic depends on `retry:`, test it against a deployed Worker, not locally.

## Verification
```bash
# Local test run
npx playwright test e2e/sse-streaming.spec.ts --headed

# CI run
WORKER_URL=http://localhost:8787 npx playwright test e2e/sse-streaming.spec.ts
```

## Related
- `streaming-sse-testing.md`
- `playwright-network-interception.md`
- `playwright-cloudflare-pages-e2e.md`
- `workers-tail-event-testing.md`
- `websocket-realtime-testing.md`

## Sources
- https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- https://developers.cloudflare.com/workers/runtime-apis/streams/readablestream/
- https://playwright.dev/docs/api/class-page#page-wait-for-function
- https://developers.cloudflare.com/workers/testing/local-development/
