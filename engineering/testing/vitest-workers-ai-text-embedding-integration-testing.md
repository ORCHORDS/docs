# Vitest Workers AI Text Embedding Integration Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a Cloudflare Worker that calls `env.AI.run('@cf/baai/bge-base-en-v1.5', ...)` to generate text
embeddings, then stores vectors in Vectorize or computes cosine similarity. Unit tests that stub
`env.AI` with a raw jest-fn produce random float arrays that cause cosine-similarity assertions to
flap non-deterministically. You need deterministic embeddings in Vitest without calling the live AI
binding.

## Context

Workers AI text-embedding models return `{ shape: number[], data: Float32Array }`. The embedding
dimension for `bge-base-en-v1.5` is 768. Code downstream of the binding normalizes vectors and
computes dot products; tests must supply geometrically valid fixtures to exercise that logic
correctly. Miniflare's `@cloudflare/vitest-pool-workers` lets you replace the AI binding with a
custom mock that returns pre-computed unit vectors, keeping tests hermetic and fast.

## 1. Vitest pool config with AI binding mock

```ts
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          // Override the real AI binding with a module-level mock
          bindings: {
            AI_MOCK: true, // flag read by setup file
          },
        },
      },
    },
    setupFiles: ['./test/setup/ai-embedding-mock.ts'],
  },
});
```

## 2. Deterministic embedding fixture factory

```ts
// test/fixtures/embeddings.ts
/**
 * Returns a unit vector of the given dimension whose components are
 * derived deterministically from `seed`. Cosine similarity between two
 * vectors with the same seed is 1.0; orthogonal seeds produce 0.0.
 */
export function deterministicEmbedding(seed: number, dim = 768): Float32Array {
  const v = new Float32Array(dim);
  // Sparse construction: only one non-zero component based on seed bucket
  const idx = seed % dim;
  v[idx] = 1.0;
  return v;
}

export interface EmbeddingResponse {
  shape: [number, number];
  data: number[];
}

export function makeEmbeddingResponse(
  texts: string[],
  dim = 768,
): EmbeddingResponse {
  const seed = texts.reduce((acc, t) => acc + t.charCodeAt(0), 0);
  const vec = deterministicEmbedding(seed, dim);
  return {
    shape: [texts.length, dim],
    data: Array.from(vec),
  };
}
```

## 3. AI binding mock setup file

```ts
// test/setup/ai-embedding-mock.ts
import { vi } from 'vitest';
import { makeEmbeddingResponse } from '../fixtures/embeddings';

// Patch globalThis so the worker env inherits the mock when
// @cloudflare/vitest-pool-workers injects bindings.
(globalThis as any).__AI_MOCK__ = {
  async run(model: string, inputs: { text: string[] }) {
    if (model.includes('bge') || model.includes('embedding')) {
      return makeEmbeddingResponse(inputs.text);
    }
    throw new Error(`AI mock: unsupported model "${model}"`);
  },
};
```

## 4. Worker under test

```ts
// src/embed.ts
export interface Env {
  AI: Ai;
}

export async function embedTexts(
  env: Env,
  texts: string[],
): Promise<number[][]> {
  const result = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: texts,
  });
  // reshape flat data into per-text vectors
  const dim = result.shape[1];
  return texts.map((_, i) =>
    (result.data as number[]).slice(i * dim, (i + 1) * dim),
  );
}

export function cosineSimilarity(a: number[], b: number[]): number {
  const dot = a.reduce((s, v, i) => s + v * b[i], 0);
  const normA = Math.sqrt(a.reduce((s, v) => s + v * v, 0));
  const normB = Math.sqrt(b.reduce((s, v) => s + v * v, 0));
  return dot / (normA * normB);
}
```

## 5. Integration tests

```ts
// test/embed.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { embedTexts, cosineSimilarity } from '../src/embed';
import { makeEmbeddingResponse } from './fixtures/embeddings';

function mockEnv(): Env {
  return {
    AI: {
      run: vi.fn().mockImplementation(
        (_model: string, inputs: { text: string[] }) =>
          Promise.resolve(makeEmbeddingResponse(inputs.text)),
      ),
    } as unknown as Ai,
  };
}

describe('embedTexts', () => {
  it('returns one vector per input text', async () => {
    const env = mockEnv();
    const vecs = await embedTexts(env, ['hello', 'world']);
    expect(vecs).toHaveLength(2);
    expect(vecs[0]).toHaveLength(768);
  });

  it('identical inputs produce cosine similarity of 1', async () => {
    const env = mockEnv();
    const [a, b] = await embedTexts(env, ['same', 'same']);
    expect(cosineSimilarity(a, b)).toBeCloseTo(1.0, 5);
  });

  it('calls AI.run with the correct model id', async () => {
    const env = mockEnv();
    await embedTexts(env, ['test']);
    expect(env.AI.run).toHaveBeenCalledWith(
      '@cf/baai/bge-base-en-v1.5',
      expect.objectContaining({ text: ['test'] }),
    );
  });
});
```

## 6. Snapshot-locking the embedding response shape

```ts
// test/embed.shape.test.ts
import { it, expect } from 'vitest';
import { makeEmbeddingResponse } from './fixtures/embeddings';

it('embedding response shape matches expected contract', () => {
  const resp = makeEmbeddingResponse(['hello world']);
  expect(resp).toMatchInlineSnapshot(`
    {
      "data": Array [/* 768 floats, one non-zero */],
      "shape": [1, 768],
    }
  `);
  expect(resp.shape[1]).toBe(768);
  expect(resp.data).toHaveLength(768);
});
```

## Anti-patterns

- **Returning `Math.random()` floats**: produces non-deterministic cosine values; assertions either
  always pass or always fail depending on the random seed.
- **Mocking at the module level with `vi.mock('../src/embed')`**: bypasses the actual `embedTexts`
  logic under test; you lose coverage of the reshape and similarity math.
- **Using the live AI binding in unit tests**: incurs network latency, quota consumption, and
  external flakiness inside the test suite.
- **Returning a plain JS `Array` instead of `Float32Array`**: causes type errors in downstream code
  that calls `.subarray()` or `.buffer` on the response.

## Gotchas

- `result.data` from the real binding is a `Float32Array`; your mock must return either a
  `Float32Array` or a plain `number[]` depending on how your worker code accesses it. Keep both
  paths covered with a type assertion in the fixture.
- `shape[0]` equals the number of input strings (batch size), not always 1. Ensure your fixture
  scales `data` length correctly: `texts.length * dim`.
- When `@cloudflare/vitest-pool-workers` runs workers in an isolated V8 context, `globalThis` in
  the setup file may differ from `globalThis` inside the worker. Inject the mock via the
  `miniflare.bindings` override or use `vi.stubGlobal` inside the worker context.
- The `bge-base-en-v1.5` model dimension is 768; `bge-small-en-v1.5` is 384. Hard-coding 768 in
  fixture factories breaks tests if you ever switch models.

## Verification

```bash
# Run embedding tests only
npx vitest run test/embed.test.ts test/embed.shape.test.ts

# Check AI.run call count and arguments
npx vitest run --reporter=verbose test/embed.test.ts

# Confirm no real network calls escape (should see 0 fetch events)
npx vitest run --reporter=verbose 2>&1 | grep -c 'fetch'
```

## Related

- `workers-ai-binding-vitest-mocking.md`
- `vitest-workers-ai-gateway-mock-testing.md`
- `miniflare-workers-ai-binding-mock-structured-output.md`
- `k6-workers-vectorize-semantic-search-load-test.md`
- `vitest-cloudflare-pool-workers.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/text-embeddings/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- https://developers.cloudflare.com/vectorize/reference/client-api/
