# Workers Memory Limit Production Incident: OOM on 15 MB JSON Payloads

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The instrument-catalogue import endpoint began returning HTTP 1101 (`Worker exceeded memory limit`) errors on roughly 8% of requests after a partner integration started sending product catalogs with embedded high-resolution cover-art encoded as base64 data-URIs. Requests completing successfully took 3–5× longer than before. The Worker process was being terminated mid-request, leaving partial imports in the database.

---

## Context

Cloudflare Workers run in V8 isolates with a hard 128 MB heap limit (as of 2025; check the current limits page). A standard `await request.json()` call buffers the entire response body into a single JavaScript string, then parses it into a V8 object graph. A 15 MB JSON file with base64 image strings expands to approximately 90–110 MB on the heap once parsed (JavaScript strings are UTF-16; the object graph overhead is significant). The Worker isolate was pushed past the 128 MB ceiling during peak loads, triggering a hard kill with error code 1101. Because the limit is per-isolate, adding more CPU via the `workers_dev` limits page does not help — memory is the bottleneck.

---

## Root Cause: `JSON.parse` of Entire Body into Heap

The problematic pattern buffers the full request body into memory before processing starts:

```typescript
// BEFORE — dangerous for large payloads
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // request.json() reads the entire body, then JSON.parse()s it.
    // For a 15 MB file this can allocate 100+ MB on the V8 heap.
    const catalog = await request.json() as CatalogPayload;

    for (const item of catalog.items) {
      // Each item may contain a 2 MB base64 image string
      await env.DB.prepare(
        'INSERT INTO products (id, name, image_b64) VALUES (?, ?, ?)'
      )
        .bind(item.id, item.name, item.image_b64)
        .run();
    }

    return new Response(JSON.stringify({ imported: catalog.items.length }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

Peak memory usage with the above pattern on a 15 MB catalog:

- Raw body buffer: ~15 MB
- JSON.parse output (UTF-16 strings + object overhead): ~95 MB
- D1 binding overhead: ~10 MB
- **Total: ~120 MB → OOM at 128 MB ceiling**

---

## Fix: Streaming JSON Parse + R2 Staging for Large Uploads

### Strategy A — Streaming parse with `@streamparser/json`

For moderately large payloads (up to ~10 MB) where streaming is feasible, use a streaming JSON parser that emits objects one at a time without buffering the entire input:

```typescript
import { parser } from '@streamparser/json';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!request.body) {
      return new Response('Missing body', { status: 400 });
    }

    const contentLength = Number(request.headers.get('content-length') ?? 0);
    if (contentLength > 20 * 1024 * 1024) {
      // For very large payloads, redirect to the R2-staging flow (Strategy B)
      return new Response(
        JSON.stringify({ error: 'payload_too_large', hint: 'use /catalog/stage' }),
        { status: 413, headers: { 'Content-Type': 'application/json' } }
      );
    }

    let imported = 0;
    const errors: string[] = [];

    // jsonparser emits a 'onValue' event for each complete JSON value
    // matched by a JSONPath selector — here we stream the `items` array.
    const jsonParser = new parser({ paths: ['$.items.*'] });

    jsonParser.onValue = async (value: unknown) => {
      const item = value as CatalogItem;
      try {
        await env.DB.prepare(
          'INSERT OR REPLACE INTO products (id, name) VALUES (?, ?)'
        )
          .bind(item.id, item.name)
          .run();
        imported++;
      } catch (err) {
        errors.push(`item ${item.id}: ${String(err)}`);
      }
    };

    const reader = request.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // Feed chunks into the streaming parser — only the current chunk
      // and the in-progress JSON token need to live on the heap.
      jsonParser.write(value);
    }

    return new Response(
      JSON.stringify({ imported, errors }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  },
};
```

### Strategy B — R2 Staging for Large Uploads

For payloads that are genuinely large (>10 MB), upload the raw file to R2 first, then process it asynchronously via a Queue or Cron Trigger. This keeps the initial Worker's heap usage near zero:

```typescript
// Step 1: Staging endpoint — just streams bytes to R2, no JSON parsing
export const stageHandler = async (
  request: Request,
  env: Env
): Promise<Response> => {
  const uploadId = crypto.randomUUID();
  const key = `catalog-imports/${uploadId}.json`;

  // R2 `put` accepts a ReadableStream — no heap allocation for the body
  await env.CATALOG_BUCKET.put(key, request.body, {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: {
      uploadedBy: request.headers.get('x-user-id') ?? 'unknown',
      uploadedAt: new Date().toISOString(),
    },
  });

  // Enqueue a processing job — the Queue message is tiny (just the key)
  await env.CATALOG_QUEUE.send({ key, uploadId });

  return new Response(
    JSON.stringify({ uploadId, status: 'queued' }),
    { status: 202, headers: { 'Content-Type': 'application/json' } }
  );
};

// Step 2: Queue consumer — runs in a separate Worker invocation with fresh heap
export const queueHandler = async (
  batch: MessageBatch<{ key: string; uploadId: string }>,
  env: Env
): Promise<void> => {
  for (const msg of batch.messages) {
    const { key, uploadId } = msg.body;
    const object = await env.CATALOG_BUCKET.get(key);
    if (!object) { msg.ack(); continue; }

    // Stream from R2 → streaming JSON parser (same pattern as Strategy A)
    const jsonParser = new parser({ paths: ['$.items.*'] });
    const importedIds: string[] = [];

    jsonParser.onValue = async (item: unknown) => {
      const product = item as CatalogItem;
      await env.DB.prepare(
        'INSERT OR REPLACE INTO products (id, name) VALUES (?, ?)'
      )
        .bind(product.id, product.name)
        .run();
      importedIds.push(product.id);
    };

    const reader = object.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      jsonParser.write(value);
    }

    // Record completion
    await env.DB.prepare(
      `UPDATE catalog_imports
          SET status = 'done', item_count = ?, completed_at = datetime('now')
        WHERE upload_id = ?`
    )
      .bind(importedIds.length, uploadId)
      .run();

    // Clean up R2 object once processed
    await env.CATALOG_BUCKET.delete(key);
    msg.ack();
  }
};
```

---

## Monitoring / Detection

```typescript
// Emit heap metrics before and after body consumption so you can track
// memory headroom. Workers expose memory diagnostics via `performance.memory`
// (non-standard V8 extension available in Workers runtime).

declare const performance: { memory?: { usedJSHeapSize: number; jsHeapSizeLimit: number } };

function heapUsageMb(): { used: number; limit: number; pct: number } | null {
  const mem = performance.memory;
  if (!mem) return null;
  const used = mem.usedJSHeapSize / 1024 / 1024;
  const limit = mem.jsHeapSizeLimit / 1024 / 1024;
  return { used, limit, pct: (used / limit) * 100 };
}

export async function trackedFetch(
  request: Request,
  env: Env
): Promise<Response> {
  const before = heapUsageMb();
  if (before) {
    console.log(`[heap] before parse: ${before.used.toFixed(1)}/${before.limit.toFixed(1)} MB (${before.pct.toFixed(0)}%)`);
    if (before.pct > 80) {
      console.warn('[heap] WARN: heap already above 80% before processing body');
    }
  }

  // ... process request ...

  const after = heapUsageMb();
  if (after) {
    console.log(`[heap] after parse: ${after.used.toFixed(1)}/${after.limit.toFixed(1)} MB (${after.pct.toFixed(0)}%)`);
  }

  return new Response('ok');
}

// Set up a Cloudflare Workers Analytics Engine metric for heap % on every request
export function emitHeapMetric(env: Env, routeName: string): void {
  const mem = heapUsageMb();
  if (!mem) return;
  env.ANALYTICS.writeDataPoint({
    blobs: ['worker_heap', routeName],
    doubles: [mem.used, mem.pct],
    indexes: ['heap_mb'],
  });
}
```

---

## Anti-patterns

- **`await request.json()` on untrusted or partner-supplied payloads** — Always check `Content-Length` before calling `.json()`, and reject anything over your safe threshold.
- **Embedding large binary data as base64 in JSON** — Base64 inflates binary size by ~33% and then JavaScript string representation adds another ~2×. Store binaries in R2 and include only a URL in JSON.
- **Processing large imports synchronously in the fetch handler** — The 30 s CPU time limit compounds with memory pressure. Offload to Queue consumers which start with fresh V8 isolates.
- **Concatenating streamed chunks into a single string** — This recreates the original problem. Pipe chunks directly into the streaming parser.

---

## Gotchas

- `@streamparser/json` version 2+ requires ESM imports; ensure your `tsconfig.json` and `wrangler.toml` are set to `"module": "esnext"`.
- R2 `put` with a `ReadableStream` body does not support `Content-Length` enforcement — implement your own byte counter in the stream transform if you need an upload size limit.
- `performance.memory` is a V8 extension not present in all runtimes; always guard with an optional check before reading it.
- Error 1101 terminates the isolate immediately; any in-flight database writes are not rolled back. Use database transactions or idempotent upserts for partial-import safety.
- The Workers heap limit applies per isolate, not per request. If a previous request on the same isolate leaked memory, your request inherits a pre-inflated heap.

---

## Verification

```bash
# Generate a synthetic 15 MB JSON catalog for local testing
node -e "
const items = Array.from({length: 500}, (_, i) => ({
  id: 'prod-' + i,
  name: 'Product ' + i,
  image_b64: Buffer.alloc(28000, 'A').toString('base64') // ~28KB base64 per item
}));
require('fs').writeFileSync('catalog-large.json', JSON.stringify({items}));
"

# Confirm file size
ls -lh catalog-large.json

# Hit the staging endpoint
curl -s -X POST https://your-worker.example.com/catalog/stage \
  -H 'Content-Type: application/json' \
  --data-binary @catalog-large.json | jq .

# Poll import status
curl -s https://your-worker.example.com/catalog/status/<uploadId> | jq .

# Check heap metrics
npx wrangler tail --format=json | jq 'select(.logs[].message | contains("[heap]"))'
```

---

## Related

- `lessons-queue-message-size-limit-exceeded.md`
- `lessons-d1-eventual-consistency-production-incident.md`

---

## Sources

- Cloudflare Workers Limits — https://developers.cloudflare.com/workers/platform/limits/#worker-limits
- `@streamparser/json` — https://github.com/juanjoDiaz/streamparser-json
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
