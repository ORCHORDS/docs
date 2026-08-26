# Streaming JSON Parsing for Large R2 Objects in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker fetches a large JSON file (product catalog, analytics export, translation bundle)
from R2. Loading the full body with `await response.json()` or `await blob.text()` causes
memory spikes that crash the isolate with a 1102 Worker error, or causes request timeouts
when the file exceeds ~128 MB. You need to process only a subset of records without
materializing the full payload in memory.

---

## Context

Cloudflare Workers have a memory limit of 128 MB per isolate. A 50 MB JSON file parsed
with `JSON.parse` may consume 3–5× its raw size in the V8 heap due to object overhead.
R2 objects are returned as `ReadableStream`, which makes streaming parse possible — but
the standard Web Streams API provides byte chunks, not JSON tokens. A streaming JSON
parser bridges the gap by emitting events as tokens arrive.

`@streamparser/json` is a zero-dependency streaming JSON parser that consumes a
`ReadableStream<Uint8Array>` and emits parsed values as they complete, including partial
array elements. It is compatible with the Workers runtime without polyfills.

**NDJSON (Newline-Delimited JSON)** — one JSON object per line — is even simpler to
stream: split on `\n`, parse each line independently.

---

## Solution

### 1. Fetching an R2 object as a stream

```typescript
import { JSONParser } from '@streamparser/json';

interface Env {
  DATA_BUCKET: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get('key') ?? 'catalog.json';

    const object = await env.DATA_BUCKET.get(key);
    if (!object) return new Response('Not found', { status: 404 });

    // object.body is a ReadableStream<Uint8Array>
    const results = await streamParseProducts(object.body);

    return Response.json({ count: results.length, items: results });
  },
};
```

### 2. Transform-as-you-parse pattern

```typescript
async function streamParseProducts(
  stream: ReadableStream<Uint8Array>,
): Promise<Product[]> {
  return new Promise((resolve, reject) => {
    const results: Product[] = [];
    const parser = new JSONParser({
      // Emit values at the array element level (root array items)
      paths: ['$.*'],
      keepStack: false,
    });

    parser.onValue = ({ value }) => {
      if (!isProduct(value)) return;

      // Filter during parse — never accumulate rejected records
      if (value.inStock && value.price < 1000) {
        results.push(normalize(value));
      }
    };

    parser.onError = (err) => reject(err);
    parser.onEnd = () => resolve(results);

    const reader = stream.getReader();

    async function pump() {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) { parser.end(); break; }
          parser.write(value);
        }
      } catch (err) {
        reject(err);
      }
    }

    pump();
  });
}

interface Product {
  id: string;
  name: string;
  price: number;
  inStock: boolean;
  category: string;
}

function isProduct(value: unknown): value is Product {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    'price' in value &&
    'inStock' in value
  );
}

function normalize(p: Product): Product {
  return { ...p, name: p.name.trim(), price: Math.round(p.price * 100) / 100 };
}
```

### 3. Memory-efficient streaming with early termination

```typescript
async function streamFindFirst(
  stream: ReadableStream<Uint8Array>,
  predicate: (item: unknown) => boolean,
): Promise<unknown | null> {
  return new Promise((resolve, reject) => {
    const parser = new JSONParser({ paths: ['$.*'], keepStack: false });
    let found = false;

    parser.onValue = ({ value }) => {
      if (found || !predicate(value)) return;
      found = true;
      // Signal the reader to cancel the stream early
      reader.cancel('found').catch(() => {});
      resolve(value);
    };

    parser.onError = (err) => { if (!found) reject(err); };
    parser.onEnd = () => { if (!found) resolve(null); };

    const reader = stream.getReader();

    (async () => {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done || found) break;
          parser.write(value);
        }
        if (!found) parser.end();
      } catch (err) {
        if (!found) reject(err);
      }
    })();
  });
}
```

### 4. NDJSON streaming (simpler, faster)

```typescript
async function* streamNDJSON(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<unknown> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        // Flush any remaining content
        if (buffer.trim()) yield JSON.parse(buffer.trim());
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // Keep the last (possibly incomplete) line in the buffer
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.trim()) yield JSON.parse(line);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// Usage:
export async function processNDJSON(env: Env, key: string): Promise<Response> {
  const object = await env.DATA_BUCKET.get(key);
  if (!object) return new Response('Not found', { status: 404 });

  let count = 0;
  let total = 0;

  for await (const record of streamNDJSON(object.body)) {
    if (typeof record === 'object' && record !== null && 'amount' in record) {
      total += (record as { amount: number }).amount;
      count++;
    }
  }

  return Response.json({ count, total });
}
```

### 5. Streaming parse with R2 range requests for large files

```typescript
async function fetchR2Range(
  bucket: R2Bucket,
  key: string,
  offset: number,
  length: number,
): Promise<R2ObjectBody | null> {
  return bucket.get(key, {
    range: { offset, length },
  });
}

// Process a 1 GB NDJSON file in 10 MB chunks
async function processLargeNDJSON(env: Env, key: string): Promise<number> {
  const head = await env.DATA_BUCKET.head(key);
  if (!head) throw new Error('Object not found');

  const CHUNK_SIZE = 10 * 1024 * 1024; // 10 MB
  let offset = 0;
  let recordCount = 0;
  let overflow = '';

  while (offset < head.size) {
    const length = Math.min(CHUNK_SIZE, head.size - offset);
    const chunk = await fetchR2Range(env.DATA_BUCKET, key, offset, length);
    if (!chunk) break;

    const text = overflow + await chunk.text();
    const lines = text.split('\n');
    overflow = lines.pop() ?? '';

    for (const line of lines) {
      if (line.trim()) recordCount++;
    }

    offset += length;
  }

  return recordCount;
}
```

---

## Implementation Details

- **`@streamparser/json` installation**: Add to `package.json`; Wrangler bundles it via
  esbuild. The library uses no Node.js built-ins and works in the Workers runtime.
- **`paths` option**: Using `$.*` instructs the parser to emit complete top-level array
  elements. For nested paths use `$.products.*.variants.*`.
- **Backpressure**: The pump loop uses `await reader.read()` sequentially, providing
  natural backpressure. Avoid buffering all chunks before starting the parser.
- **Decoder stream**: For `TextDecoder`, always pass `{ stream: true }` when decoding
  chunks to handle multi-byte UTF-8 sequences split across chunk boundaries.

---

## Anti-patterns

- **`await object.text()` on large objects**: Materializes the entire file in memory.
  Safe only for files under ~5 MB.
- **`await object.json()`**: Same issue — reads the whole body before parsing.
- **Accumulating all results**: If the goal is to count, aggregate, or stream output,
  never collect results into an array. Emit them incrementally.
- **Using `JSON.parse` inside the chunk loop**: Chunks are not valid JSON fragments.
  You must use a streaming parser or accumulate full lines (NDJSON only).

---

## Gotchas

- R2 `get()` returns `null` for missing keys, not a 404 `Response`. Always null-check.
- The Workers CPU time limit (50 ms for free, 30 s for paid) includes parsing. A 500 MB
  file may exceed limits regardless of memory. Use R2 Select or pre-process offline.
- `reader.cancel()` on an R2 stream closes the underlying HTTP connection to R2 storage.
  This is desirable for early termination but logs a cancel event in R2 metrics.
- NDJSON line buffers can grow unbounded if lines are very long. Add a max-line-length
  guard: `if (buffer.length > MAX_LINE) throw new Error('Line too long')`.

---

## Verification

```typescript
// Unit test: stream a synthetic large NDJSON
const lines = Array.from({ length: 100_000 }, (_, i) =>
  JSON.stringify({ id: i, amount: Math.random() * 100 })
).join('\n');

const stream = new ReadableStream<Uint8Array>({
  start(controller) {
    // Feed in 4 KB chunks to simulate network
    const encoder = new TextEncoder();
    const data = encoder.encode(lines);
    for (let i = 0; i < data.length; i += 4096) {
      controller.enqueue(data.slice(i, i + 4096));
    }
    controller.close();
  },
});

let count = 0;
for await (const _ of streamNDJSON(stream)) count++;
console.assert(count === 100_000, `Expected 100000, got ${count}`);
```

```bash
# Measure memory with Wrangler tail
wrangler tail --format pretty | grep -E 'cpu_time|memory'
```

---

## Related

- `workers-kv-bulk-prefetch-pattern.md`
- `workers-d1-read-replica-pattern.md`
- `lazy-load-images-r2-srcset.md`
- `workers-streaming-response-time-to-first-byte.md`

---

## Sources

- @streamparser/json — https://github.com/juanjoDiaz/streamparser-json
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare Workers limits — https://developers.cloudflare.com/workers/platform/limits/
- NDJSON specification — https://ndjson.org/
