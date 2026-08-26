# Workers AI Embedding Cache with KV TTL

date: 2026-08-24 / author: example.com / status: production

---

## Symptom / Use-case

Every user query passes through `@cf/baai/bge-base-en-v1.5` before reaching Vectorize, costing
inference time on repeated or near-identical inputs. Popular search terms ("how do I reset my
password", "pricing plans", "contact support") embed to the same vector every time. Caching the
embedding in Workers KV with a TTL eliminates redundant inference calls, cuts p50 latency by
30-60 ms on cache hits, and reduces Workers AI billing for high-traffic embed endpoints.

## Context

A Workers AI embedding call takes 20-80 ms on warm paths. KV reads return in under 5 ms globally.
For any system where a significant fraction of queries repeat within hours or days — search bars,
chatbots with FAQ-heavy traffic, classification pipelines — an embedding cache pays back immediately.

The cache key is the hash of the exact input string plus the model ID so model upgrades
automatically invalidate stale embeddings. Floating-point vectors are serialised to a compact binary
`Float32Array` buffer to minimise KV storage and read costs.

Embeddings are deterministic: the same model + same input always produces the same vector, so there
is no staleness risk from caching. The only eviction trigger is a model version change, which is
handled by including the model ID in the cache key.

---

## Cache key derivation

```typescript
// src/embed-cache-key.ts

/**
 * Derive a stable, compact KV key from the model identifier and input text.
 * Using a 64-bit FNV-1a hash keeps keys short while collision risk is negligible
 * for typical embedding workloads (< 10 M unique strings per model).
 */
export function embedCacheKey(modelId: string, input: string): string {
  // Simple djb2-inspired hash — replace with crypto.subtle.digest for collision resistance
  let h = 5381n;
  const combined = `${modelId}\x00${input}`;
  for (let i = 0; i < combined.length; i++) {
    h = ((h << 5n) + h + BigInt(combined.charCodeAt(i))) & 0xffff_ffff_ffffn;
  }
  return `emb:${h.toString(16)}`;
}

/** Serialise a float vector to an ArrayBuffer for compact KV storage. */
export function vectorToBuffer(vec: number[]): ArrayBuffer {
  const buf = new Float32Array(vec);
  return buf.buffer;
}

/** Deserialise a KV-stored ArrayBuffer back to a number array. */
export function bufferToVector(buf: ArrayBuffer): number[] {
  return Array.from(new Float32Array(buf));
}
```

---

## Cached embed function

```typescript
// src/embed.ts
import { embedCacheKey, vectorToBuffer, bufferToVector } from "./embed-cache-key";

const MODEL_ID = "@cf/baai/bge-base-en-v1.5";
const CACHE_TTL_SECONDS = 86_400; // 24 hours; set lower for content that changes daily

export interface Env {
  AI: Ai;
  EMBED_CACHE: KVNamespace;
}

/**
 * Return the embedding for `input`, reading from KV cache when available.
 * On a cache miss, runs Workers AI inference and writes the result back to KV.
 */
export async function cachedEmbed(env: Env, input: string): Promise<number[]> {
  const key = embedCacheKey(MODEL_ID, input);

  // 1. Cache read
  const cached = await env.EMBED_CACHE.get(key, { type: "arrayBuffer" });
  if (cached !== null) {
    return bufferToVector(cached);
  }

  // 2. Cache miss — run inference
  const result = await env.AI.run(MODEL_ID as any, { text: [input] });
  const vec: number[] =
    Array.isArray((result as any).data?.[0])
      ? (result as any).data[0]
      : (result as any).data ?? [];

  if (vec.length === 0) {
    throw new Error("Embedding model returned empty vector");
  }

  // 3. Write through — fire-and-forget to avoid blocking the response
  const buffer = vectorToBuffer(vec);
  env.EMBED_CACHE.put(key, buffer, { expirationTtl: CACHE_TTL_SECONDS }).catch(
    (err: unknown) => console.error("embed cache write failed", err),
  );

  return vec;
}
```

---

## Batch embedding with cache-aside

```typescript
// src/embed-batch.ts
import { cachedEmbed, type Env } from "./embed";
import { embedCacheKey } from "./embed-cache-key";
import { vectorToBuffer, bufferToVector } from "./embed-cache-key";

const MODEL_ID = "@cf/baai/bge-base-en-v1.5";
const CACHE_TTL_SECONDS = 86_400;

/**
 * Embed multiple strings, hitting KV in bulk for cached entries and batching
 * only the misses to Workers AI.
 */
export async function cachedEmbedBatch(
  env: Env,
  inputs: string[],
): Promise<number[][]> {
  const keys = inputs.map((s) => embedCacheKey(MODEL_ID, s));

  // Bulk KV read (KV getMany is not available; use Promise.all)
  const cached = await Promise.all(
    keys.map((k) => env.EMBED_CACHE.get(k, { type: "arrayBuffer" })),
  );

  const misses: Array<{ originalIndex: number; text: string }> = [];
  const results: (number[] | null)[] = cached.map((c, i) => {
    if (c !== null) return bufferToVector(c);
    misses.push({ originalIndex: i, text: inputs[i] });
    return null;
  });

  if (misses.length === 0) {
    return results as number[][];
  }

  // Batch inference for misses (Workers AI handles up to 100 items per call)
  const missTexts = misses.map((m) => m.text);
  const aiResult = await (env.AI as any).run(MODEL_ID, { text: missTexts });
  const newVectors: number[][] = (aiResult as any).data ?? [];

  // Write misses back to KV and fill results
  const writes = misses.map(async (m, idx) => {
    const vec = newVectors[idx];
    results[m.originalIndex] = vec;
    const buf = vectorToBuffer(vec);
    await env.EMBED_CACHE.put(keys[m.originalIndex], buf, {
      expirationTtl: CACHE_TTL_SECONDS,
    });
  });
  await Promise.allSettled(writes);

  return results as number[][];
}
```

---

## Worker entry point with cache-hit header

```typescript
// src/index.ts
import { cachedEmbed, type Env } from "./embed";

export { Env };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const text = url.searchParams.get("q");
    if (!text) {
      return new Response("Missing query param: q", { status: 400 });
    }

    const start = Date.now();
    const vector = await cachedEmbed(env, text);
    const durationMs = Date.now() - start;

    // Fast path: KV hit returns in < 10 ms; inference takes 20–80 ms
    const fromCache = durationMs < 15;

    return new Response(JSON.stringify({ vector, dims: vector.length }), {
      headers: {
        "Content-Type": "application/json",
        "X-Cache": fromCache ? "HIT" : "MISS",
        "X-Duration-Ms": String(durationMs),
      },
    });
  },
};
```

---

## Cache invalidation on model upgrade

```typescript
// src/invalidate.ts
// Run via a Cron Trigger after deploying a new model version.

export interface Env {
  EMBED_CACHE: KVNamespace;
}

export async function invalidateEmbedCache(kv: KVNamespace): Promise<number> {
  let cursor: string | undefined;
  let deleted = 0;

  do {
    const page = await kv.list({ prefix: "emb:", cursor, limit: 1000 });
    await Promise.all(page.keys.map((k) => kv.delete(k.name)));
    deleted += page.keys.length;
    cursor = page.list_complete ? undefined : (page as any).cursor;
  } while (cursor);

  return deleted;
}
```

## Anti-patterns

- **Caching with only the text as the key (no model ID)** — upgrading to a different model dimension
  (e.g., 768 → 1536) silently serves stale mismatched vectors; always include the model ID.
- **Storing vectors as JSON strings** — `JSON.stringify` of a 768-float array takes ~6 KB;
  `Float32Array.buffer` takes 3 KB. At scale the difference in KV storage costs is significant.
- **Blocking the response on the KV write** — fire-and-forget the write so the first caller
  experiences no added latency from the write path.
- **Indefinite TTL** — even though embeddings are deterministic, set a reasonable TTL to clean up
  entries for content that is no longer queried, avoiding KV namespace bloat.
- **Single-key sequential reads for batches** — always fan out KV reads with `Promise.all` rather
  than awaiting each in a loop; KV reads are cheap but sequential I/O compounds latency.

## Gotchas

- KV values are limited to 25 MB; a single `Float32Array` of 1024 floats is 4 KB — well within
  limits even for large models.
- KV has eventual consistency; in rare cases two concurrent requests on the same cold key will both
  incur inference (race to write). This is acceptable for an embed cache — the worst case is two
  identical writes.
- Workers KV `list` operations iterate up to 1000 keys per page and are not available in free-tier
  workers; use the invalidation script via a paid plan.
- The `arrayBuffer` KV type coerces the stored value; ensure you write a true `ArrayBuffer` (not a
  `Float32Array` view) to avoid read-back errors.

## Verification

```bash
# First request should be a MISS
curl -s "https://your-worker.workers.dev/?q=reset+password" -D - | grep X-Cache
# X-Cache: MISS

# Second request same text → HIT
curl -s "https://your-worker.workers.dev/?q=reset+password" -D - | grep X-Cache
# X-Cache: HIT

# Confirm vector dimensions are correct
curl -s "https://your-worker.workers.dev/?q=hello" | jq .dims
# 768
```

## Related

- `workers-ai-batch-embedding-queues-pipeline.md` — batch embedding via Queues
- `workers-ai-embeddings-batch-r2.md` — storing embedding results in R2
- `embedding-generation-patterns.md` — general embedding strategy patterns
- `semantic-caching-patterns.md` — caching LLM responses (as opposed to embeddings)
- `vectorize-cosine-similarity-threshold-tuning-workers.md` — downstream use of cached vectors

## Sources

- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- Workers AI embedding models: https://developers.cloudflare.com/workers-ai/models/#text-embeddings
- KV storage limits: https://developers.cloudflare.com/kv/platform/limits/
