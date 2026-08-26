# Vitest Cloudflare Analytics Engine Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your Worker writes custom metrics to Cloudflare Analytics Engine via
`env.ANALYTICS.writeDataPoint()`. You want to assert that the right blobs, doubles,
and indexes are written for specific request paths — without depending on Cloudflare's
GraphQL API or real billing-tier access.

## Context

Analytics Engine (AE) exposes a write-only binding (`AnalyticsEngineDataset`) in the
Worker runtime. There is no read-back API in the binding itself; data is queried via
GraphQL after an ingestion delay. For unit tests, the binding must be mocked to capture
calls. `@cloudflare/vitest-pool-workers` does not synthesise AE writes in Miniflare, so
the canonical approach is to inject a typed spy via `env` overrides.

## Vitest Config

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

## Worker Under Test

```ts
// src/index.ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);

    const response = await handleRequest(request, env);

    const latencyMs = Date.now() - start;
    env.ANALYTICS.writeDataPoint({
      blobs: [url.pathname, request.method, String(response.status)],
      doubles: [latencyMs],
      indexes: [env.REGION ?? "global"],
    });

    return response;
  },
};

async function handleRequest(request: Request, env: Env): Promise<Response> {
  return new Response("OK");
}
```

## Typed Mock for AnalyticsEngineDataset

```ts
// test/helpers/mock-analytics.ts
import { vi } from "vitest";

export interface CapturedDataPoint {
  blobs: string[];
  doubles: number[];
  indexes: string[];
}

export function createMockAnalytics() {
  const written: CapturedDataPoint[] = [];

  const dataset: AnalyticsEngineDataset = {
    writeDataPoint(data: AnalyticsEngineDataPoint) {
      written.push({
        blobs: (data.blobs ?? []).map(String),
        doubles: (data.doubles ?? []).map(Number),
        indexes: (data.indexes ?? []).map(String),
      });
    },
  };

  return { dataset, written };
}
```

## Testing Blob Fields

```ts
// test/analytics-blobs.test.ts
import { describe, it, expect } from "vitest";
import worker from "../src/index";
import { createMockAnalytics } from "./helpers/mock-analytics";

describe("Analytics Engine blobs", () => {
  it("writes pathname, method, and status as blobs", async () => {
    const { dataset, written } = createMockAnalytics();
    const env = { ANALYTICS: dataset, REGION: "eu-west" } as unknown as Env;

    await worker.fetch(
      new Request("https://example.com/api/users", { method: "GET" }),
      env,
      { waitUntil: () => {}, passThroughOnException: () => {} } as ExecutionContext
    );

    expect(written).toHaveLength(1);
    expect(written[0].blobs).toEqual(["/api/users", "GET", "200"]);
  });
});
```

## Testing Double Fields (Latency)

```ts
// test/analytics-doubles.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/index";
import { createMockAnalytics } from "./helpers/mock-analytics";

describe("Analytics Engine doubles", () => {
  it("records latency as a non-negative double", async () => {
    vi.useFakeTimers();
    const { dataset, written } = createMockAnalytics();
    const env = { ANALYTICS: dataset } as unknown as Env;

    const fetchPromise = worker.fetch(
      new Request("https://example.com/ping"),
      env,
      { waitUntil: () => {}, passThroughOnException: () => {} } as ExecutionContext
    );
    vi.advanceTimersByTime(42);
    await fetchPromise;

    expect(written[0].doubles[0]).toBeGreaterThanOrEqual(0);
    vi.useRealTimers();
  });
});
```

## Testing Index Fields

```ts
// test/analytics-indexes.test.ts
import { describe, it, expect } from "vitest";
import worker from "../src/index";
import { createMockAnalytics } from "./helpers/mock-analytics";

describe("Analytics Engine indexes", () => {
  it("uses env.REGION as the index", async () => {
    const { dataset, written } = createMockAnalytics();
    const env = { ANALYTICS: dataset, REGION: "apac" } as unknown as Env;

    await worker.fetch(
      new Request("https://example.com/"),
      env,
      { waitUntil: () => {}, passThroughOnException: () => {} } as ExecutionContext
    );

    expect(written[0].indexes).toEqual(["apac"]);
  });

  it("falls back to 'global' when REGION is not set", async () => {
    const { dataset, written } = createMockAnalytics();
    const env = { ANALYTICS: dataset } as unknown as Env;

    await worker.fetch(
      new Request("https://example.com/"),
      env,
      { waitUntil: () => {}, passThroughOnException: () => {} } as ExecutionContext
    );

    expect(written[0].indexes).toEqual(["global"]);
  });
});
```

## Testing That No Points Are Written on Error Paths

```ts
// test/analytics-error-path.test.ts
import { describe, it, expect, vi } from "vitest";
import { createMockAnalytics } from "./helpers/mock-analytics";

describe("Analytics Engine error suppression", () => {
  it("does not write a data point when the handler throws", async () => {
    const { dataset, written } = createMockAnalytics();

    async function errorWorker(req: Request, env: any, ctx: any) {
      try {
        throw new Error("upstream failure");
      } catch {
        // handler throws, no writeDataPoint called
        return new Response("error", { status: 500 });
      }
    }

    const env = { ANALYTICS: dataset } as unknown as Env;
    await errorWorker(new Request("https://example.com/"), env, {});
    expect(written).toHaveLength(0);
  });
});
```

## Anti-patterns

- **Asserting on real AE GraphQL responses in tests**: The ingestion pipeline has a
  delay of minutes; unit tests cannot use it for fast feedback.
- **Mocking only `writeDataPoint` and ignoring the shape**: Type the mock return using
  `AnalyticsEngineDataPoint` so TypeScript catches schema drift early.
- **Calling `writeDataPoint` outside `ctx.waitUntil()`**: In production the Worker
  may return before the write completes if it is async; use `ctx.waitUntil()` to ensure
  the write is flushed, and await those promises in tests.

## Gotchas

- `AnalyticsEngineDataset` is write-only at runtime. Do not attempt to read back values
  from the binding — that path does not exist.
- Each `writeDataPoint` call accepts up to 20 blobs, 20 doubles, and 1 index. Tests
  that exceed those limits should expect the runtime to silently drop excess fields.
- The binding name (`ANALYTICS`) must be declared in `wrangler.toml` under
  `[analytics_engine_datasets]` for `wrangler deploy`; the mock bypasses this in tests.

## Verification

```bash
npx vitest run test/analytics-blobs.test.ts test/analytics-doubles.test.ts \
  test/analytics-indexes.test.ts test/analytics-error-path.test.ts
```

All suites should pass. Add `--coverage` and verify the branch that falls back to
`"global"` is exercised.

## Related

- `observability-driven-testing-traces.md`
- `workers-tail-event-testing.md`
- `vitest-cloudflare-pool-workers.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
