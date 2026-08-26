# Workers AI Embedding Cache with KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A semantic search endpoint calls `ai.run('@cf/baai/bge-small-en-v1.5', { text })` for every incoming query. Workers AI embedding latency ranges from 80–300 ms per call. Under moderate load (100 req/s) that single line exhausts most of the CPU time budget and adds visible latency. Identical or near-identical queries — site search, product lookup, autocomplete — re-embed text that was just embedded 200 ms ago.

## Context

Workers AI embeddings are deterministic: the same model + same input text always produce the same float vector. This makes them ideal candidates for content-addressable caching. KV is the right store: it tolerates eventual consistency (stale embeddings are harmless for search), supports TTL-based expiration, and reads complete in ~5–10 ms globally from within a Worker. The cache key is a SHA-256 digest of `model + normalized_text`, stored as a base64 string. The value is the raw embedding buffer compressed with `CompressionStream`.

---

## Cache Key Design

Normalize the input text before hashing to collapse trivially equivalent inputs.

```typescript
async function embeddingCacheKey(model: string, text: string): Promise<string> {
  // Normalize: lowercase, collapse whitespace, trim
  const normalized = text.toLowerCase().replace(/\s+/g, ' ').trim();
  const raw = `${model}:${normalized}`;

  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  // Base64url — safe as a KV key, no slashes or padding issues
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
```

## Serialize and Compress the Embedding

`bge-small-en-v1.5` produces 384 float32 values = 1,536 bytes raw. Gzip brings this to ~1,100 bytes. KV value size limit is 25 MB, but smaller values reduce read latency.

```typescript
async function serializeEmbedding(vector: number[]): Promise<ArrayBuffer> {
  const float32 = new Float32Array(vector);
  const raw = new Uint8Array(float32.buffer);

  const cs = new CompressionStream('gzip');
  const writer = cs.writable.getWriter();
  writer.write(raw);
  writer.close();
  return new Response(cs.readable).arrayBuffer();
}

async function deserializeEmbedding(compressed: ArrayBuffer): Promise<number[]> {
  const ds = new DecompressionStream('gzip');
  const writer = ds.writable.getWriter();
  writer.write(new Uint8Array(compressed));
  writer.close();
  const raw = await new Response(ds.readable).arrayBuffer();
  return Array.from(new Float32Array(raw));
}
```

## Cache-Aside Read/Write Pattern

```typescript
const EMBEDDING_MODEL = '@cf/baai/bge-small-en-v1.5';
const CACHE_TTL_SECONDS = 60 * 60 * 24 * 7; // 7 days

async function getEmbedding(
  text: string,
  env: Env
): Promise<number[]> {
  const key = await embeddingCacheKey(EMBEDDING_MODEL, text);

  // 1. KV read (~5–10 ms)
  const cached = await env.EMBEDDINGS_KV.get(key, { type: 'arrayBuffer' });
  if (cached) {
    return deserializeEmbedding(cached);
  }

  // 2. Workers AI call (~80–300 ms)
  const result = await env.AI.run(EMBEDDING_MODEL, { text });
  const vector: number[] = result.data[0];

  // 3. Write-behind: store in KV without blocking response
  const compressed = await serializeEmbedding(vector);
  // Use waitUntil so the KV write doesn't add to response latency
  // (caller must pass ctx)
  env._ctx.waitUntil(
    env.EMBEDDINGS_KV.put(key, compressed, { expirationTtl: CACHE_TTL_SECONDS })
  );

  return vector;
}
```

## Integrating `waitUntil` via Context Passing

Pass the `ExecutionContext` through so write-behind works without blocking.

```typescript
export interface Env {
  AI: Ai;
  EMBEDDINGS_KV: KVNamespace;
  _ctx: ExecutionContext; // set in fetch handler
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    env._ctx = ctx; // attach context for write-behind

    const { query } = await request.json<{ query: string }>();
    const vector = await getEmbedding(query, env);

    // Use vector for similarity search against Vectorize or D1
    const results = await env.VECTORIZE.query(vector, { topK: 10 });
    return Response.json(results);
  },
};
```

## Batch Embedding with Coalesced KV Reads

For bulk embedding (e.g., indexing documents), resolve all KV reads in one pass.

```typescript
async function batchGetEmbeddings(
  texts: string[],
  env: Env
): Promise<number[][]> {
  // 1. Compute all keys in parallel
  const keys = await Promise.all(texts.map(t => embeddingCacheKey(EMBEDDING_MODEL, t)));

  // 2. KV bulk read — getWithMetadata supports up to 128 keys via list,
  //    but direct bulk reads require individual gets in parallel
  const kvResults = await Promise.all(
    keys.map(k => env.EMBEDDINGS_KV.get(k, { type: 'arrayBuffer' }))
  );

  // 3. Identify misses
  const misses: number[] = [];
  kvResults.forEach((v, i) => { if (!v) misses.push(i); });

  if (misses.length > 0) {
    // Batch Workers AI call for all misses
    const missTexts = misses.map(i => texts[i]);
    const aiResult = await env.AI.run(EMBEDDING_MODEL, { text: missTexts });

    // Fill results and write to KV
    await Promise.all(misses.map(async (idx, j) => {
      const vector = aiResult.data[j];
      const buf = await serializeEmbedding(vector);
      kvResults[idx] = buf;
      env._ctx.waitUntil(
        env.EMBEDDINGS_KV.put(keys[idx], buf, { expirationTtl: CACHE_TTL_SECONDS })
      );
    }));
  }

  return Promise.all(
    kvResults.map((buf) => deserializeEmbedding(buf!))
  );
}
```

## Cache Hit Rate Monitoring

```typescript
async function getEmbeddingWithMetrics(
  text: string,
  env: Env
): Promise<{ vector: number[]; cacheHit: boolean }> {
  const key = await embeddingCacheKey(EMBEDDING_MODEL, text);
  const cached = await env.EMBEDDINGS_KV.get(key, { type: 'arrayBuffer' });

  if (cached) {
    env._ctx.waitUntil(
      env.ANALYTICS.writeDataPoint({ blobs: ['embedding_hit'], doubles: [1] })
    );
    return { vector: await deserializeEmbedding(cached), cacheHit: true };
  }

  const result = await env.AI.run(EMBEDDING_MODEL, { text });
  env._ctx.waitUntil(
    env.ANALYTICS.writeDataPoint({ blobs: ['embedding_miss'], doubles: [1] })
  );
  return { vector: result.data[0], cacheHit: false };
}
```

---

## Anti-patterns

- **Using the raw text as the KV key**: Long queries exceed the 512-byte KV key limit and include characters that corrupt key parsing. Always hash.
- **Storing JSON-encoded arrays**: `JSON.stringify([0.123, ...])` for 384 floats produces ~3 KB vs 1.5 KB binary. Use `Float32Array` + compression.
- **Blocking the response on KV writes**: Awaiting the `put()` before returning adds 20–50 ms. Use `waitUntil()` for write-behind.
- **Setting no TTL**: Embeddings from retired model versions accumulate forever. Set a TTL that exceeds your model redeployment cadence (7–30 days).
- **Caching embeddings across model versions**: A model update changes vector geometry. Namespace the cache key with the model ID.

---

## Gotchas

- Workers AI `run()` with an array `text` field batches multiple texts in one call — but only models that accept array inputs support this. `bge-small-en-v1.5` does; verify with the model spec before batching.
- KV `get()` with `{ type: 'arrayBuffer' }` returns `null` on a miss, not an empty buffer. Always null-check before passing to `deserializeEmbedding`.
- `CompressionStream('gzip')` is available in Workers runtime. `CompressionStream('brotli')` is not available as of mid-2026. Use `gzip` or `deflate`.
- KV eventual consistency means a freshly written embedding may not be visible from a different edge node for up to 60 seconds. This is acceptable for embeddings but not for access-control data.

---

## Verification

```bash
# Check cache hit rate after deploying
wrangler tail --format json | jq 'select(.logs[].message | test("embedding_"))'
```

Confirm p50 latency drops from ~150 ms to ~10 ms for repeat queries in Cloudflare Analytics or Workers Metrics.

```typescript
// Unit test: serialization round-trip
const original = Array.from({ length: 384 }, () => Math.random() - 0.5);
const buf = await serializeEmbedding(original);
const restored = await deserializeEmbedding(buf);
const maxDelta = Math.max(...original.map((v, i) => Math.abs(v - restored[i])));
console.assert(maxDelta < 1e-6, 'Float32 round-trip should be lossless');
```

---

## Related

- `workers-ai-inference-response-caching.md` — caching full inference responses
- `workers-ai-batch-inference-throughput.md` — batching AI calls for throughput
- `kv-read-performance.md` — KV read latency characteristics
- `vectorize-query-latency-optimization.md` — using cached embeddings with Vectorize

---

## Sources

- Cloudflare Workers AI embedding models: https://developers.cloudflare.com/workers-ai/models/text-embeddings/
- KV limits (key max 512 bytes, value max 25 MB): https://developers.cloudflare.com/kv/platform/limits/
- Workers `CompressionStream` support: https://developers.cloudflare.com/workers/runtime-apis/web-standards/#compression-streams
- `waitUntil` background tasks: https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
