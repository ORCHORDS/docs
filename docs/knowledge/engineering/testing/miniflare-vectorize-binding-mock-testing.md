# Miniflare Vectorize Binding Mock Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers that use Vectorize for semantic search, RAG pipelines, or recommendation engines need
deterministic unit tests without hitting the production Vectorize index. Miniflare v3 does not
ship a native Vectorize binding simulator, so teams either skip the layer entirely or wire up
fragile HTTP mocks that don't match the SDK surface. This article shows how to build a full
in-process Vectorize mock that satisfies the `VectorizeIndex` interface and integrates cleanly
with `@cloudflare/vitest-pool-workers`.

## Context

Vectorize bindings expose `insert`, `upsert`, `query`, `getByIds`, `deleteByIds`, and
`describe` as async methods. Each method operates on `VectorizeVector` objects (id, values,
optional metadata, optional namespace). The mock must honour the cosine / euclidean / dot
distance functions so nearest-neighbour assertions remain meaningful in tests, yet run entirely
in-memory without network I/O. The example project platform uses Vectorize for content embeddings in
the search service (`apps/search-worker`) and for user personalisation in the recommendation
engine (`apps/reco-worker`).

---

## In-Memory VectorizeIndex Implementation

```typescript
// test/mocks/vectorize.ts
import type {
  VectorizeIndex,
  VectorizeVector,
  VectorizeMatches,
  VectorizeMatch,
  VectorizeQueryOptions,
  VectorizeIndexDetails,
} from "@cloudflare/workers-types";

type StoredVector = VectorizeVector & { namespace?: string };

function cosine(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB) || 1);
}

function euclidean(a: number[], b: number[]): number {
  return Math.sqrt(a.reduce((s, v, i) => s + (v - b[i]) ** 2, 0));
}

function dotProduct(a: number[], b: number[]): number {
  return a.reduce((s, v, i) => s + v * b[i], 0);
}

export type VectorizeMetric = "cosine" | "euclidean" | "dot-product";

export function createMockVectorizeIndex(
  dimensions = 768,
  metric: VectorizeMetric = "cosine"
): VectorizeIndex & { _store: Map<string, StoredVector>; _calls: string[] } {
  const store = new Map<string, StoredVector>();
  const calls: string[] = [];

  function score(a: number[], b: number[]): number {
    switch (metric) {
      case "euclidean":   return -euclidean(a, b);   // negate: lower = closer
      case "dot-product": return dotProduct(a, b);
      default:            return cosine(a, b);
    }
  }

  return {
    _store: store,
    _calls: calls,

    async insert(vectors: VectorizeVector[]) {
      calls.push("insert");
      for (const v of vectors) {
        if (v.values.length !== dimensions)
          throw new Error(`Expected ${dimensions}D, got ${v.values.length}D`);
        store.set(v.id, { ...v });
      }
      return { count: vectors.length, ids: vectors.map((v) => v.id) };
    },

    async upsert(vectors: VectorizeVector[]) {
      calls.push("upsert");
      for (const v of vectors) store.set(v.id, { ...v });
      return { count: vectors.length, ids: vectors.map((v) => v.id) };
    },

    async query(
      vector: number[],
      options: VectorizeQueryOptions = {}
    ): Promise<VectorizeMatches> {
      calls.push("query");
      const { topK = 3, namespace, returnValues = false, returnMetadata = false } = options;
      const candidates = [...store.values()].filter(
        (v) => !namespace || v.namespace === namespace
      );
      const scored: VectorizeMatch[] = candidates
        .map((v) => ({
          id: v.id,
          score: score(vector, v.values as number[]),
          values: returnValues ? v.values : undefined,
          metadata: returnMetadata ? v.metadata : undefined,
        }))
        .sort((a, b) => b.score - a.score)
        .slice(0, topK);
      return { matches: scored, count: scored.length };
    },

    async getByIds(ids: string[]): Promise<VectorizeVector[]> {
      calls.push("getByIds");
      return ids.flatMap((id) => (store.has(id) ? [store.get(id)!] : []));
    },

    async deleteByIds(ids: string[]): Promise<{ count: number; ids: string[] }> {
      calls.push("deleteByIds");
      const deleted: string[] = [];
      for (const id of ids) {
        if (store.delete(id)) deleted.push(id);
      }
      return { count: deleted.length, ids: deleted };
    },

    async describe(): Promise<VectorizeIndexDetails> {
      calls.push("describe");
      return {
        name: "mock-index",
        dimensions,
        metric,
        vectorsCount: store.size,
      } as VectorizeIndexDetails;
    },
  };
}
```

---

## Wiring the Mock into the Miniflare Environment

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // Override bindings declared in wrangler.toml
        miniflare: {
          vectorizeIndexes: {
            // Miniflare accepts plain objects that satisfy the VectorizeIndex interface
            CONTENT_VECTORS: (env: unknown) =>
              import("./test/mocks/vectorize").then(({ createMockVectorizeIndex }) =>
                createMockVectorizeIndex(768, "cosine")
              ),
          },
        },
      },
    },
  },
});
```

> Because Miniflare delegates to the object you supply, the mock runs in the same V8 isolate
> as the Worker — no serialization overhead, no port management.

---

## Writing Vectorize Unit Tests

```typescript
// test/search-worker.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { env, SELF } from "cloudflare:test";
import { createMockVectorizeIndex } from "./mocks/vectorize";

// Helper: random unit vector
function randVec(dim = 768): number[] {
  const v = Array.from({ length: dim }, () => Math.random() - 0.5);
  const norm = Math.sqrt(v.reduce((s, x) => s + x * x, 0));
  return v.map((x) => x / norm);
}

describe("search worker – vectorize", () => {
  const idx = createMockVectorizeIndex(768, "cosine");

  beforeEach(() => {
    idx._store.clear();
    idx._calls.length = 0;
  });

  it("inserts and queries nearest neighbours", async () => {
    const target = randVec();
    const close = target.map((x) => x + 0.01); // slightly perturbed
    const far   = randVec();                    // random, likely distant

    await idx.upsert([
      { id: "doc-1", values: target },
      { id: "doc-2", values: close },
      { id: "doc-3", values: far },
    ]);

    const results = await idx.query(target, { topK: 2 });
    const ids = results.matches.map((m) => m.id);

    expect(ids).toContain("doc-1");
    expect(ids).toContain("doc-2");
    expect(ids).not.toContain("doc-3");
  });

  it("respects namespace isolation", async () => {
    await idx.upsert([
      { id: "a", values: randVec(), namespace: "en" },
      { id: "b", values: randVec(), namespace: "fr" },
    ]);
    const res = await idx.query(randVec(), { topK: 5, namespace: "en" });
    expect(res.matches.every((m) => m.id === "a")).toBe(true);
  });

  it("tracks method calls for assertion", async () => {
    await idx.describe();
    await idx.insert([{ id: "x", values: randVec() }]);
    expect(idx._calls).toEqual(["describe", "insert"]);
  });
});
```

---

## Testing the Worker Handler End-to-End

```typescript
// test/search-worker-e2e.test.ts
import { it, expect, beforeAll } from "vitest";
import { SELF } from "cloudflare:test";

// The worker's /search endpoint calls env.CONTENT_VECTORS.query internally
beforeAll(async () => {
  // Seed via the worker's /seed endpoint (only enabled in test builds)
  await SELF.fetch("http://localhost/seed", {
    method: "POST",
    body: JSON.stringify([
      { id: "art-1", values: Array(768).fill(0.1), metadata: { title: "Hello World" } },
      { id: "art-2", values: Array(768).fill(0.9), metadata: { title: "Advanced Topics" } },
    ]),
    headers: { "Content-Type": "application/json" },
  });
});

it("returns ranked results from /search", async () => {
  const res = await SELF.fetch("http://localhost/search", {
    method: "POST",
    body: JSON.stringify({ query: "hello", topK: 1 }),
    headers: { "Content-Type": "application/json" },
  });
  expect(res.status).toBe(200);
  const json = await res.json<{ results: { id: string }[] }>();
  expect(json.results[0].id).toBe("art-1");
});
```

---

## Simulating Vectorize Errors

```typescript
// test/vectorize-error.test.ts
import { it, expect, vi } from "vitest";
import { createMockVectorizeIndex } from "./mocks/vectorize";

it("worker returns 503 when Vectorize query fails", async () => {
  const { SELF, env } = await import("cloudflare:test");

  vi.spyOn(env.CONTENT_VECTORS as ReturnType<typeof createMockVectorizeIndex>, "query")
    .mockRejectedValueOnce(new Error("upstream timeout"));

  const res = await SELF.fetch("http://localhost/search", {
    method: "POST",
    body: JSON.stringify({ query: "crash me" }),
    headers: { "Content-Type": "application/json" },
  });
  expect(res.status).toBe(503);
});
```

---

## Anti-patterns

- **Mocking `fetch` instead of the binding** – Vectorize is not HTTP from inside the Worker
  runtime; the binding is a native object. Intercepting outbound `fetch` misses the actual
  call path.
- **Sharing mock state across tests** – `_store` is a plain `Map`; always `clear()` in
  `beforeEach`. Leaking vectors causes false positives in distance comparisons.
- **Ignoring dimension mismatch** – Production Vectorize rejects vectors with wrong
  dimensions. Enforce the same check in the mock constructor to catch bugs early.
- **Using all-zeros vectors in tests** – Cosine of zero is undefined. Use `randVec()` or
  deliberate unit vectors; never `Array(768).fill(0)` as the query vector.
- **Not testing namespace isolation** – Namespaces are a first-class Vectorize feature;
  skip them in tests and production namespace bugs go undetected.

---

## Gotchas

- Miniflare 3 does not validate that the object you supply is a real `VectorizeIndex`; type
  safety comes entirely from TypeScript. Cast carefully.
- `returnValues` and `returnMetadata` on `query` options must be honoured or tests that
  destructure match payloads will get `undefined` properties silently.
- `score` ordering: for euclidean metric, smaller distance = better match. The mock negates
  the distance before sorting so `topK` semantics remain consistent regardless of metric.
- Vectorize `insert` is idempotent per id in production but raises if you call `insert`
  twice with the same id in some SDK versions. Test `upsert` as the safe default.
- The `describe()` method returning `vectorsCount` reflects real production behaviour only
  after the next index segment flush (≤ 60 s delay). The mock returns live count; don't
  assert count immediately after insert in integration tests against real Vectorize.

---

## Verification

```bash
# Run only Vectorize-related tests
pnpm vitest run --reporter=verbose test/search-worker.test.ts test/vectorize-error.test.ts

# Type-check the mock against the workers-types VectorizeIndex interface
pnpm tsc --noEmit --strict

# Coverage: ensure vectorize branch paths are exercised
pnpm vitest run --coverage test/search-worker.test.ts
```

Expected output: all tests green, zero type errors, ≥ 85% branch coverage on the search
handler module.

---

## Related

- `miniflare-workers-ai-binding-mock-structured-output.md`
- `vitest-workers-ai-gateway-mock-testing.md`
- `k6-workers-vectorize-semantic-search-load-test.md`
- `vitest-cloudflare-pool-workers.md`
- `miniflare-d1-integration-testing.md`

---

## Sources

- Cloudflare Vectorize docs: https://developers.cloudflare.com/vectorize/
- `@cloudflare/workers-types` VectorizeIndex interface (2025-11 snapshot)
- Miniflare v3 binding injection: https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare
- `@cloudflare/vitest-pool-workers` pool options: https://developers.cloudflare.com/workers/testing/vitest-integration/
