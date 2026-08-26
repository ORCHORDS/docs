# Testing A/B Experiment Assignment Logic in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker assigns users to A/B experiment buckets using `crypto.getRandomValues` and persists the assignment in KV so users get a consistent experience across requests. You need to verify that bucket assignment percentages match configuration, that KV stickiness works, and that QA teams can bypass assignment via a request header — all without making real random calls or deploying to production.

---

## Context

Workers have access to the Web Crypto API's `crypto.getRandomValues`, which is not mockable via `vi.spyOn` alone because it is a built-in global. The standard pattern is to wrap the random call in an injectable function so tests can substitute a deterministic implementation. Bucket assignment logic distributes users across variants by mapping a `[0, 1)` float to cumulative percentage thresholds (e.g. 0–0.5 → control, 0.5–0.8 → variant-a, 0.8–1.0 → variant-b). Statistical correctness is verified with a chi-square goodness-of-fit test run in the Node environment that hosts Vitest's test runner. KV stickiness means the first assignment is stored under a user-scoped key and returned on all subsequent requests without re-rolling.

---

## Setup / Config

`wrangler.toml`:
```toml
[[kv_namespaces]]
binding = "EXPERIMENTS"
id = "00000000000000000000000000000002"
```

`vitest.config.ts`:
```typescript
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          kvNamespaces: ["EXPERIMENTS"],
        },
      },
    },
  },
});
```

`src/experiment.ts`:
```typescript
export interface ExperimentConfig {
  /** e.g. { control: 0.5, "variant-a": 0.3, "variant-b": 0.2 } — must sum to 1.0 */
  buckets: Record<string, number>;
}

/** Seeded random: injectable for tests */
export type RandomFn = () => number;

export const defaultRandom: RandomFn = () => {
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return buf[0] / (0xffffffff + 1);
};

export function assignBucket(
  config: ExperimentConfig,
  random: RandomFn = defaultRandom
): string {
  const roll = random();
  let cumulative = 0;

  for (const [bucket, weight] of Object.entries(config.buckets)) {
    cumulative += weight;
    if (roll < cumulative) return bucket;
  }

  // Fallback: return the last bucket (handles floating-point edge cases)
  return Object.keys(config.buckets).at(-1)!;
}

export interface Env {
  EXPERIMENTS: KVNamespace;
}

const EXPERIMENT_CONFIG: ExperimentConfig = {
  buckets: { control: 0.5, "variant-a": 0.3, "variant-b": 0.2 },
};

export default {
  async fetch(
    request: Request,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<Response> {
    const userId = request.headers.get("x-user-id");
    if (!userId) return new Response("Missing x-user-id", { status: 400 });

    // QA override: allow forcing a specific bucket
    const override = request.headers.get("x-qa-bucket");
    if (override && Object.keys(EXPERIMENT_CONFIG.buckets).includes(override)) {
      return new Response(JSON.stringify({ bucket: override, source: "override" }));
    }

    // Check for sticky assignment in KV
    const kvKey = `experiment:homepage:${userId}`;
    const stored = await env.EXPERIMENTS.get(kvKey);
    if (stored) {
      return new Response(JSON.stringify({ bucket: stored, source: "sticky" }));
    }

    // First visit — assign and persist
    const bucket = assignBucket(EXPERIMENT_CONFIG);
    await env.EXPERIMENTS.put(kvKey, bucket, { expirationTtl: 60 * 60 * 24 * 30 });

    return new Response(JSON.stringify({ bucket, source: "assigned" }));
  },
};
```

---

## Test Implementation

`src/experiment.test.ts`:
```typescript
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, afterEach } from "vitest";
import { assignBucket, type ExperimentConfig } from "./experiment";

// ---------------------------------------------------------------------------
// Chi-square goodness-of-fit (runs in Node, not Workers runtime)
// ---------------------------------------------------------------------------
function chiSquare(
  observed: Record<string, number>,
  expected: Record<string, number>,
  total: number
): number {
  return Object.keys(expected).reduce((sum, key) => {
    const o = observed[key] ?? 0;
    const e = expected[key] * total;
    return sum + (o - e) ** 2 / e;
  }, 0);
}

// ---------------------------------------------------------------------------
// Deterministic random factory
// ---------------------------------------------------------------------------
function makeSeededRandom(values: number[]): () => number {
  let i = 0;
  return () => values[i++ % values.length];
}

const TEST_CONFIG: ExperimentConfig = {
  buckets: { control: 0.5, "variant-a": 0.3, "variant-b": 0.2 },
};

afterEach(async () => {
  // KV cleanup: delete any keys written during the test
  const keys = await env.EXPERIMENTS.list({ prefix: "experiment:" });
  await Promise.all(keys.keys.map((k) => env.EXPERIMENTS.delete(k.name)));
});

describe("assignBucket()", () => {
  it("assigns to 'control' when roll < 0.5", () => {
    const random = makeSeededRandom([0.0, 0.1, 0.49]);
    for (let i = 0; i < 3; i++) {
      expect(assignBucket(TEST_CONFIG, random)).toBe("control");
    }
  });

  it("assigns to 'variant-a' when 0.5 <= roll < 0.8", () => {
    const random = makeSeededRandom([0.5, 0.65, 0.799]);
    for (let i = 0; i < 3; i++) {
      expect(assignBucket(TEST_CONFIG, random)).toBe("variant-a");
    }
  });

  it("assigns to 'variant-b' when 0.8 <= roll < 1.0", () => {
    const random = makeSeededRandom([0.8, 0.9, 0.9999]);
    for (let i = 0; i < 3; i++) {
      expect(assignBucket(TEST_CONFIG, random)).toBe("variant-b");
    }
  });

  it("distribution matches configured weights (chi-square p > 0.05)", () => {
    // N = 10 000 samples for stable chi-square result
    const N = 10_000;
    const counts: Record<string, number> = { control: 0, "variant-a": 0, "variant-b": 0 };

    // Use a simple LCG for speed; it is seeded so the test is deterministic
    let seed = 42;
    const lcg = (): number => {
      seed = (seed * 1664525 + 1013904223) & 0xffffffff;
      return ((seed >>> 0) & 0x7fffffff) / 0x7fffffff;
    };

    for (let i = 0; i < N; i++) {
      const bucket = assignBucket(TEST_CONFIG, lcg);
      counts[bucket]++;
    }

    const chi2 = chiSquare(counts, TEST_CONFIG.buckets, N);

    // chi2 critical value at df=2, p=0.05 is 5.991
    // A well-implemented assigner should produce chi2 << 5.991
    expect(chi2).toBeLessThan(5.991);
  });
});

describe("fetch() handler — sticky assignment", () => {
  it("returns 'assigned' source on first request and stores KV", async () => {
    const res = await SELF.fetch(new Request("http://example.com/", {
      headers: { "x-user-id": "user-123" },
    }));
    const body = await res.json<{ bucket: string; source: string }>();

    expect(res.status).toBe(200);
    expect(["control", "variant-a", "variant-b"]).toContain(body.bucket);
    expect(body.source).toBe("assigned");

    // Confirm KV was written
    const stored = await env.EXPERIMENTS.get("experiment:homepage:user-123");
    expect(stored).toBe(body.bucket);
  });

  it("returns 'sticky' source on second request with same user", async () => {
    // Seed a pre-existing assignment
    await env.EXPERIMENTS.put("experiment:homepage:user-456", "variant-a");

    const res = await SELF.fetch(new Request("http://example.com/", {
      headers: { "x-user-id": "user-456" },
    }));
    const body = await res.json<{ bucket: string; source: string }>();

    expect(body.bucket).toBe("variant-a");
    expect(body.source).toBe("sticky");
  });

  it("QA override header bypasses random and KV", async () => {
    const res = await SELF.fetch(new Request("http://example.com/", {
      headers: {
        "x-user-id": "qa-engineer",
        "x-qa-bucket": "variant-b",
      },
    }));
    const body = await res.json<{ bucket: string; source: string }>();

    expect(body.bucket).toBe("variant-b");
    expect(body.source).toBe("override");

    // KV should NOT have been written for the override
    const stored = await env.EXPERIMENTS.get("experiment:homepage:qa-engineer");
    expect(stored).toBeNull();
  });

  it("rejects unknown override bucket values", async () => {
    // 'hacked-bucket' is not in the config — should fall through to normal assignment
    const res = await SELF.fetch(new Request("http://example.com/", {
      headers: {
        "x-user-id": "attacker",
        "x-qa-bucket": "hacked-bucket",
      },
    }));
    const body = await res.json<{ bucket: string; source: string }>();

    // Falls back to real assignment — source must not be 'override'
    expect(body.source).not.toBe("override");
    expect(["control", "variant-a", "variant-b"]).toContain(body.bucket);
  });

  it("returns 400 when x-user-id header is absent", async () => {
    const res = await SELF.fetch(new Request("http://example.com/"));
    expect(res.status).toBe(400);
  });
});
```

---

## Anti-patterns

- **Mocking `crypto.getRandomValues` globally** — the Workers runtime does not expose the global `crypto` object through `vi.spyOn`; inject the random function as a parameter instead.
- **Using `Math.random()` in production code** — `Math.random` in Workers is not cryptographically random and its seeding behaviour is undefined; always use `crypto.getRandomValues`.
- **Asserting exact bucket counts in distribution tests** — counts vary by sample size and seed; use a statistical threshold (chi-square) instead of exact equality.
- **Not cleaning up KV between tests** — stale sticky assignments leak into subsequent test assertions; always delete written keys in `afterEach`.
- **Storing the QA override in KV** — override headers are for ephemeral QA use; persisting them would contaminate production data for real users.

---

## Gotchas

- The chi-square test requires a minimum expected count per cell of ~5; with `N = 10 000` and the smallest bucket at 20%, the expected count is 2000 — well above the threshold.
- `crypto.getRandomValues` fills a typed array in-place and returns it; extracting a `[0,1)` float requires dividing by `0xFFFFFFFF + 1` (not `0xFFFFFFFF`) to avoid the value exactly equalling 1.
- KV `list()` in Miniflare returns only keys that were set in the current session; it does not pre-populate from `wrangler.toml` KV IDs.
- `SELF` from `cloudflare:test` dispatches requests to the Worker under test including all bindings — it is the correct way to integration-test full request/response cycles in `vitest-pool-workers`.
- The `expirationTtl` parameter to `kv.put()` has no effect in local Miniflare; keys do not expire in tests.

---

## Verification

```bash
# Run experiment tests
npx vitest run src/experiment.test.ts

# Run with verbose output to see chi-square value
npx vitest run --reporter=verbose src/experiment.test.ts

# Manually inspect KV assignments in local dev
npx wrangler kv key list --namespace-id 00000000000000000000000000000002 --local
```

---

## Related

- `workers-queue-consumer-testing-vitest.md`
- `workers-email-handler-testing-miniflare.md`

---

## Sources

- Cloudflare Workers Crypto API — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- Cloudflare KV Docs — https://developers.cloudflare.com/kv/
- Vitest Pool Workers SELF — https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
- Chi-square test reference — https://en.wikipedia.org/wiki/Chi-squared_test
