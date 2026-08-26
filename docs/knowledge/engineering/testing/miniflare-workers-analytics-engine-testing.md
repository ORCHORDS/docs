# Miniflare Workers Analytics Engine Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project uses Cloudflare Workers Analytics Engine (WAE) to record anonymous engagement events —
post views, reactions, and share counts — without storing PII. Because WAE writes are fire-and-forget
from the Worker's perspective, tests that only assert on HTTP response status codes can miss
incorrect event schemas, wrong dataset names, or missing fields that cause WAE to silently drop
events. The team needed a way to assert that `writeDataPoint` is called with the correct blobs and
doubles inside unit/integration tests using Miniflare directly (not via the vitest pool adapter).

## Context

`@miniflare/core` (v3) exposes an `AnalyticsEngine` binding stub in its `MiniflareOptions` through
the `analyticsEngines` map. When a binding is configured, Miniflare records each `writeDataPoint`
call in an in-memory log accessible via `miniflare.getAnalyticsEngineDataset(bindingName)`. This
gives precise per-test assertions on the exact data points written, including blob and double values,
without needing a real WAE dataset or sending HTTP requests to the Cloudflare API.

## Worker Event Recording

```typescript
// src/analytics/events.ts
import { Env } from "../types";

export interface PageViewEvent {
  postId: string;
  anonCountry: string;
  reactionCount: number;
  shareCount: number;
}

export function recordPageView(event: PageViewEvent, env: Env): void {
  // Fire-and-forget: do NOT await this
  env.ANALYTICS.writeDataPoint({
    blobs: [event.postId, event.anonCountry],
    doubles: [event.reactionCount, event.shareCount],
    indexes: [event.postId],
  });
}

export function recordReaction(
  postId: string,
  reactionType: string,
  env: Env
): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [postId, reactionType],
    doubles: [1],
    indexes: [postId],
  });
}
```

## Miniflare Test Setup

```typescript
// tests/integration/analytics-engine-setup.ts
import { Miniflare } from "miniflare";

export function createTestMiniflare(): Miniflare {
  return new Miniflare({
    modules: true,
    scriptPath: "./dist/worker.js", // built by wrangler before tests
    analyticsEngines: {
      // Binding name must match wrangler.toml [[analytics_engine_datasets]]
      ANALYTICS: { dataset: "example project_events_test" },
    },
    kvNamespaces: ["SESSION_KV"],
    compatibilityDate: "2024-09-23",
    compatibilityFlags: ["nodejs_compat"],
  });
}
```

## Analytics Engine Assertions

```typescript
// tests/integration/analytics-engine.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { Miniflare } from "miniflare";
import { createTestMiniflare } from "./analytics-engine-setup";

describe("Analytics Engine data point recording", () => {
  let mf: Miniflare;

  beforeAll(async () => {
    mf = createTestMiniflare();
    await mf.ready;
  });

  afterAll(async () => {
    await mf.dispose();
  });

  it("records a page view data point with correct blobs and doubles", async () => {
    // Trigger the Worker endpoint that calls recordPageView
    await mf.dispatchFetch("https://worker.test/posts/abc123", {
      method: "GET",
      headers: { "CF-IPCountry": "DE", "x-anon-token": "test-token" },
    });

    const dataset = await mf.getAnalyticsEngineDataset("ANALYTICS");
    const dataPoints = await dataset.getDataPoints();

    expect(dataPoints).toHaveLength(1);

    const [dp] = dataPoints;
    expect(dp.blobs[0]).toBe("abc123");       // postId
    expect(dp.blobs[1]).toBe("DE");            // anonCountry
    expect(dp.doubles[0]).toBeGreaterThanOrEqual(0); // reactionCount
    expect(dp.indexes[0]).toBe("abc123");
  });

  it("records a reaction data point with type blob", async () => {
    await mf.dispatchFetch("https://worker.test/posts/abc123/react", {
      method: "POST",
      body: JSON.stringify({ reaction: "fire" }),
      headers: { "Content-Type": "application/json", "x-anon-token": "test" },
    });

    const dataset = await mf.getAnalyticsEngineDataset("ANALYTICS");
    const dataPoints = await dataset.getDataPoints();

    // Filter to reaction events (blob[1] is the reaction type, not a country code)
    const reactionPoints = dataPoints.filter(
      (dp) => dp.blobs[1] === "fire"
    );
    expect(reactionPoints).toHaveLength(1);
    expect(reactionPoints[0].doubles[0]).toBe(1);
  });

  it("does not write any data points for unauthenticated requests", async () => {
    await mf.dispatchFetch("https://worker.test/posts/abc123", {
      method: "GET",
      // No x-anon-token header
    });

    const dataset = await mf.getAnalyticsEngineDataset("ANALYTICS");
    const dataPoints = await dataset.getDataPoints();

    // Unauthenticated requests should not emit analytics events
    expect(
      dataPoints.filter((dp) => dp.blobs[0] === "abc123")
    ).toHaveLength(0);
  });
});
```

## Isolating Data Points Between Tests

Because Miniflare's in-memory WAE dataset accumulates across requests in the same Miniflare
instance, tests need to isolate their assertions by index or by creating a fresh Miniflare per test.
The index field makes filtering by `postId` reliable when multiple test cases share one instance.

```typescript
// tests/integration/analytics-reset.test.ts
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Miniflare } from "miniflare";
import { createTestMiniflare } from "./analytics-engine-setup";

describe("Analytics Engine — isolated per test", () => {
  let mf: Miniflare;

  beforeEach(async () => {
    // Fresh Miniflare instance per test ensures a clean WAE in-memory store
    mf = createTestMiniflare();
    await mf.ready;
  });

  afterEach(async () => {
    await mf.dispose();
  });

  it("records exactly one data point per page view", async () => {
    const postId = `post-${crypto.randomUUID()}`;
    await mf.dispatchFetch(`https://worker.test/posts/${postId}`, {
      headers: { "x-anon-token": "tok" },
    });

    const dataset = await mf.getAnalyticsEngineDataset("ANALYTICS");
    const all = await dataset.getDataPoints();
    expect(all.filter((dp) => dp.indexes[0] === postId)).toHaveLength(1);
  });
});
```

## Asserting Schema Correctness (Blob Count, Double Count)

WAE silently drops data points with too many blobs (>20) or doubles (>20). Add a schema assertion
helper to catch schema drift early:

```typescript
// tests/helpers/wae-schema-guard.ts
export interface WaeDataPoint {
  blobs: (string | null)[];
  doubles: number[];
  indexes: (string | null)[];
}

export function assertWaeSchema(
  dp: WaeDataPoint,
  expected: { blobCount: number; doubleCount: number }
): void {
  if (dp.blobs.length > 20) {
    throw new Error(`WAE: blob count ${dp.blobs.length} exceeds limit of 20`);
  }
  if (dp.doubles.length > 20) {
    throw new Error(
      `WAE: double count ${dp.doubles.length} exceeds limit of 20`
    );
  }
  if (dp.blobs.filter(Boolean).length !== expected.blobCount) {
    throw new Error(
      `WAE: expected ${expected.blobCount} non-null blobs, got ${dp.blobs.filter(Boolean).length}`
    );
  }
  if (dp.doubles.length !== expected.doubleCount) {
    throw new Error(
      `WAE: expected ${expected.doubleCount} doubles, got ${dp.doubles.length}`
    );
  }
}
```

## Anti-patterns

- Asserting on WAE by checking response bodies — `writeDataPoint` is fire-and-forget; the HTTP response is independent of whether the data point was accepted.
- Using `vi.spyOn(env.ANALYTICS, "writeDataPoint")` without Miniflare — spies on the binding object do not simulate schema validation or the in-memory log.
- Sharing a single Miniflare instance across all test files without clearing WAE state — data points accumulate and `toHaveLength` assertions become order-dependent.
- Naming the test dataset the same as production — use a distinct name (`example project_events_test`) so local test runs never appear in production WAE dashboards.

## Gotchas

- `mf.getAnalyticsEngineDataset` returns a Miniflare-specific API; it is not available inside the Worker script itself — use it only in the test host (Node.js / vitest context).
- `await mf.ready` is required before dispatching fetch; skipping it causes Miniflare to accept the dispatch but the Worker may not yet have the bindings wired.
- The `analyticsEngines` Miniflare option key must match the binding name in `wrangler.toml` under `[[analytics_engine_datasets]] binding = "ANALYTICS"`.
- Data points are written asynchronously by the runtime even though `writeDataPoint` returns `undefined` synchronously — add a small `await new Promise(r => setTimeout(r, 10))` before asserting if the Worker dispatches work in a `waitUntil`.

## Verification

```bash
# Build the Worker first (Miniflare needs the compiled output)
npx wrangler build --env test

# Run the integration tests
npx vitest run tests/integration/analytics-engine.test.ts \
  tests/integration/analytics-reset.test.ts
```

## Related

- documentation/docs/policies/testing/vitest-analytics-engine-testing.md
- documentation/docs/policies/testing/miniflare-multi-worker-environment-setup.md
- documentation/docs/policies/testing/vitest-cloudflare-pool-workers.md
- documentation/docs/policies/testing/observability-driven-testing-traces.md

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- https://miniflare.dev/core/analytics-engine
- https://developers.cloudflare.com/workers/testing/miniflare/
