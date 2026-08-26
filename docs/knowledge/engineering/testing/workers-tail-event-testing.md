# Workers Tail Event Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You ship a Cloudflare Worker with a `tail()` handler to forward structured logs to an
observability back-end (e.g. Axiom, Datadog, Honeycomb). Unit tests cover the business
logic, but the tail handler itself — fan-out, filtering, enrichment, retries — goes
untested until it breaks silently in production.

## Context

Workers tail handlers receive a `TraceItem[]` array carrying `logs`, `exceptions`,
`outcome`, and `scriptName` for each completed invocation. The handler runs in a
separate isolate after the originating request is done, so it cannot affect response
latency. Miniflare 3 / `@cloudflare/vitest-pool-workers` does not yet run a second
isolate for tail, so the practical approach is to call `tail()` as an ordinary async
function in Vitest, handing it crafted `TraceItem` fixtures.

## Setting Up Vitest with Workers Pool

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
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

## Crafting TraceItem Fixtures

```ts
// test/fixtures/trace-items.ts
import type { TraceItem } from "@cloudflare/workers-types";

export function makeTraceItem(
  overrides: Partial<TraceItem> = {}
): TraceItem {
  return {
    scriptName: "my-worker",
    outcome: "ok",
    eventTimestamp: Date.now(),
    logs: [],
    exceptions: [],
    diagnosticsChannelEvents: [],
    event: {
      request: {
        url: "https://example.com/api",
        method: "GET",
        headers: {},
        cf: {} as CfProperties,
      },
    },
    ...overrides,
  };
}
```

## Testing Log Fan-out

```ts
// test/tail.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import worker from "../src/index";
import { makeTraceItem } from "./fixtures/trace-items";

const mockFetch = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => mockFetch.mockClear());

describe("tail() fan-out", () => {
  it("posts each trace to the analytics endpoint", async () => {
    const items = [makeTraceItem(), makeTraceItem({ scriptName: "edge-fn" })];

    await worker.tail!(items, {} as ExecutionContext, {} as Env);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("https://ingest.example.com/logs");
    const body = JSON.parse(init.body as string);
    expect(body.events).toHaveLength(2);
  });
});
```

## Testing Exception Capture

```ts
// test/tail-exceptions.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/index";
import { makeTraceItem } from "./fixtures/trace-items";

const mockFetch = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
vi.stubGlobal("fetch", mockFetch);

describe("tail() exception capture", () => {
  it("extracts exception messages into the payload", async () => {
    const item = makeTraceItem({
      outcome: "exception",
      exceptions: [{ name: "TypeError", message: "Cannot read properties of null" }],
    });

    await worker.tail!([item], {} as ExecutionContext, {} as Env);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body as string);
    expect(body.events[0].error).toBe("TypeError: Cannot read properties of null");
  });
});
```

## Testing Filtering Logic

```ts
// test/tail-filter.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/index";
import { makeTraceItem } from "./fixtures/trace-items";

const mockFetch = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
vi.stubGlobal("fetch", mockFetch);

describe("tail() outcome filtering", () => {
  it("drops 'canceled' outcomes before forwarding", async () => {
    const items = [
      makeTraceItem({ outcome: "ok" }),
      makeTraceItem({ outcome: "canceled" }),
    ];

    await worker.tail!([items[0]], {} as ExecutionContext, {} as Env);
    const body = JSON.parse(mockFetch.mock.calls[0][1].body as string);
    expect(body.events).toHaveLength(1);
    expect(body.events[0].outcome).toBe("ok");
  });
});
```

## Testing Retry on Upstream Failure

```ts
// test/tail-retry.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/index";
import { makeTraceItem } from "./fixtures/trace-items";

describe("tail() upstream retry", () => {
  it("retries once on 503 then succeeds", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", mockFetch);

    await worker.tail!([makeTraceItem()], {} as ExecutionContext, {} as Env);

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});
```

## Anti-patterns

- **Relying on wrangler tail for CI**: `wrangler tail` streams live events; it is not
  reproducible in automated pipelines. Use fixture-driven unit tests.
- **Testing tail by inspecting side-effects inside `fetch()`**: Couple tests to the
  observable HTTP contract (URL, headers, body shape), not internal implementation
  details like helper functions.
- **Ignoring the `ExecutionContext`**: If your tail handler calls `ctx.waitUntil()`,
  collect those promises and `await` them explicitly in tests to avoid false passes.

## Gotchas

- `tail()` receives a **snapshot** of logs at handler completion; `console.log` calls
  inside the tail handler itself do NOT appear in the same batch.
- Wrangler's `tail_consumers` config in `wrangler.toml` is separate from unit tests;
  your test harness must wire up the tail export manually.
- `TraceItem.event` may be `null` for scheduled (cron) invocations; guard against it
  to avoid runtime `TypeError` in production.

## Verification

```bash
npx vitest run test/tail.test.ts test/tail-exceptions.test.ts \
  test/tail-filter.test.ts test/tail-retry.test.ts
```

All four suites should show green. Add `--coverage` to confirm the `tail` export branch
reaches ≥ 90 % statement coverage.

## Related

- `workers-cron-trigger-integration-testing.md`
- `workers-queues-retry-dlq-testing.md`
- `observability-driven-testing-traces.md`

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
