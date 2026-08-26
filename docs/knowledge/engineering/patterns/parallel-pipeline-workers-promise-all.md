# Parallel Processing Pipelines with Promise.all in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to process a collection of independent items — enriching records, running
validations, calling multiple downstream services, or transforming assets — where
each item's work is independent of the others but you still need all results before
responding. Doing this sequentially is slow; naive `Promise.all` on large arrays
hits memory limits or subrequest caps; and scatter-gather patterns focus on querying
multiple upstreams, not processing one collection through multiple stages.

## Context

Workers run in a single-threaded event loop, but `await` yields control, so
concurrent async operations execute interleaved, not truly parallel. The CPU is
shared across in-flight promises within one Worker invocation. The practical
implications:

- **Subrequest limit**: 50 concurrent subrequests per Worker invocation (fetch to
  external URLs). KV, D1, R2, Queue, and service binding calls do not count.
- **CPU time**: 10ms for the free tier, 30s for paid (with `duration` enabled). CPU
  usage during awaited I/O does not count; only synchronous computation counts.
- **Memory**: 128 MB per invocation. Materializing large result sets eats into this.

The pattern here is a typed, stage-based pipeline: input items flow through
configurable stages, each stage runs items concurrently within a concurrency limit,
and stages can be chained sequentially. This gives you fine-grained control over
resource usage versus throughput.

---

## Concurrency-Controlled Map

A raw `Promise.all(items.map(fn))` fires all items simultaneously. For large arrays
or subrequest-heavy work, cap concurrency with a semaphore-like pool.

```typescript
// src/pipeline.ts

/**
 * Process `items` through `fn` with at most `concurrency` in-flight at once.
 * Returns results in input order (same guarantee as Promise.all).
 */
export async function pMap<T, R>(
  items: T[],
  fn: (item: T, index: number) => Promise<R>,
  concurrency: number
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let nextIndex = 0;

  async function worker(): Promise<void> {
    while (nextIndex < items.length) {
      const i = nextIndex++;
      results[i] = await fn(items[i], i);
    }
  }

  // Spin up `concurrency` workers; each drains the shared queue
  const workers = Array.from({ length: Math.min(concurrency, items.length) }, worker);
  await Promise.all(workers);
  return results;
}

/**
 * Same as pMap but collects errors without short-circuiting.
 * Returns a discriminated union array preserving order.
 */
export async function pMapSettled<T, R>(
  items: T[],
  fn: (item: T, index: number) => Promise<R>,
  concurrency: number
): Promise<Array<{ ok: true; value: R } | { ok: false; error: unknown }>> {
  return pMap(
    items,
    async (item, i) => {
      try {
        return { ok: true as const, value: await fn(item, i) };
      } catch (error) {
        return { ok: false as const, error };
      }
    },
    concurrency
  );
}
```

## Multi-Stage Pipeline

```typescript
// src/pipeline.ts (continued)

export type Stage<In, Out> = {
  name: string;
  concurrency: number;
  run: (item: In) => Promise<Out>;
};

export type PipelineResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: unknown; item: unknown };

/**
 * Run a multi-stage pipeline.
 * Each stage processes the successful outputs of the previous stage.
 * Items that fail at any stage are collected as errors and do not continue.
 */
export async function runPipeline<TInput, TOutput>(
  items: TInput[],
  stages: [Stage<TInput, any>, ...Stage<any, any>[], Stage<any, TOutput>]
): Promise<{ succeeded: TOutput[]; failed: PipelineResult<TOutput>[] }> {
  let current: Array<{ ok: true; value: unknown } | { ok: false; error: unknown; item: unknown }> =
    items.map((value) => ({ ok: true as const, value }));

  const failed: PipelineResult<TOutput>[] = [];

  for (const stage of stages) {
    const pending = current.filter((r) => r.ok) as Array<{ ok: true; value: unknown }>;
    const alreadyFailed = current.filter((r) => !r.ok) as Array<{ ok: false; error: unknown; item: unknown }>;
    failed.push(...(alreadyFailed as PipelineResult<TOutput>[]));

    const stageResults = await pMapSettled(
      pending.map((r) => r.value),
      stage.run,
      stage.concurrency
    );

    current = stageResults.map((r, i) =>
      r.ok
        ? { ok: true as const, value: r.value }
        : { ok: false as const, error: r.error, item: pending[i].value }
    );
  }

  const lastFailed = current.filter((r) => !r.ok) as PipelineResult<TOutput>[];
  const succeeded = (current.filter((r) => r.ok) as Array<{ ok: true; value: TOutput }>).map(
    (r) => r.value
  );

  failed.push(...lastFailed);
  return { succeeded, failed };
}
```

## Concrete Example: Batch Record Enrichment

Enrich a list of product IDs by fetching inventory from a service binding, pricing
from D1, and generating signed R2 image URLs — all in a three-stage pipeline.

```typescript
// src/enrich-worker.ts
import { Env } from "./types";
import { runPipeline, Stage } from "./pipeline";

interface RawProduct { id: string; name: string; imageKey: string }
interface WithInventory extends RawProduct { stock: number }
interface WithPricing extends WithInventory { priceCents: number; currency: string }
interface EnrichedProduct extends WithPricing { imageUrl: string }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { productIds } = await request.json<{ productIds: string[] }>();
    if (productIds.length > 200) {
      return Response.json({ error: "Max 200 products per request" }, { status: 400 });
    }

    // Stage 0: fetch raw records from D1 (bulk — single query, not per-item)
    const placeholders = productIds.map(() => "?").join(",");
    const { results: raw } = await env.DB.prepare(
      `SELECT id, name, image_key AS imageKey FROM products WHERE id IN (${placeholders})`
    ).bind(...productIds).all<RawProduct>();

    // Stage 1: enrich with inventory via service binding (concurrency 10)
    const stageInventory: Stage<RawProduct, WithInventory> = {
      name: "inventory",
      concurrency: 10,
      run: async (product) => {
        const res = await env.INVENTORY_WORKER.fetch(
          new Request(`https://internal/stock/${product.id}`)
        );
        const { stock } = await res.json<{ stock: number }>();
        return { ...product, stock };
      },
    };

    // Stage 2: fetch pricing from D1 (concurrency 5, D1 calls don't count against subrequest limit)
    const stagePricing: Stage<WithInventory, WithPricing> = {
      name: "pricing",
      concurrency: 5,
      run: async (product) => {
        const price = await env.DB.prepare(
          "SELECT price_cents AS priceCents, currency FROM prices WHERE product_id = ?"
        ).bind(product.id).first<{ priceCents: number; currency: string }>();
        return { ...product, priceCents: price?.priceCents ?? 0, currency: price?.currency ?? "USD" };
      },
    };

    // Stage 3: generate presigned R2 image URLs (concurrency 20 — R2 calls are fast)
    const stageImages: Stage<WithPricing, EnrichedProduct> = {
      name: "images",
      concurrency: 20,
      run: async (product) => {
        const url = await env.PRODUCT_IMAGES.createPresignedUrl("GET", product.imageKey, {
          expiresIn: 3600,
        });
        return { ...product, imageUrl: url };
      },
    };

    const { succeeded, failed } = await runPipeline(raw, [stageInventory, stagePricing, stageImages]);

    return Response.json({
      products: succeeded,
      errors: failed.map((f) => ({
        item: (f as any).item,
        error: String((f as any).error),
      })),
    });
  },
};
```

## Chunked Processing for Large Collections

When items exceed what fits in memory or the 50-subrequest limit within one
invocation, chunk the work across Queue messages.

```typescript
// src/bulk-processor.ts
import { Env } from "./types";
import { pMap } from "./pipeline";

const CHUNK_SIZE = 50;

export default {
  // API entry: splits into chunks, enqueues each
  async fetch(request: Request, env: Env): Promise<Response> {
    const { jobId, itemIds } = await request.json<{ jobId: string; itemIds: string[] }>();

    const chunks: string[][] = [];
    for (let i = 0; i < itemIds.length; i += CHUNK_SIZE) {
      chunks.push(itemIds.slice(i, i + CHUNK_SIZE));
    }

    await pMap(
      chunks,
      async (chunk, i) => {
        await env.PROCESSING_QUEUE.send({ jobId, chunkIndex: i, itemIds: chunk });
      },
      10 // 10 concurrent Queue sends
    );

    return Response.json({ jobId, totalChunks: chunks.length }, { status: 202 });
  },

  // Queue consumer: processes one chunk with concurrency inside the Worker
  async queue(batch: MessageBatch<{ jobId: string; chunkIndex: number; itemIds: string[] }>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { jobId, chunkIndex, itemIds } = msg.body;

      const results = await pMapSettled(itemIds, async (id) => processItem(id, env), 10);

      const failed = results.filter((r) => !r.ok).length;
      console.log(`Job ${jobId} chunk ${chunkIndex}: ${results.length - failed} ok, ${failed} failed`);
      msg.ack();
    }
  },
};

async function processItem(id: string, env: Env): Promise<void> {
  // placeholder for real per-item work
  await env.DB.prepare("UPDATE items SET processed_at = ? WHERE id = ?").bind(Date.now(), id).run();
}
```

## Anti-patterns

- **`Promise.all(items.map(fn))` with no concurrency cap on large arrays**: fires
  100+ subrequests simultaneously, hitting the 50-concurrent-subrequest limit and
  causing silent drops or 429s from downstream.
- **Sequential `for await` loops when items are independent**: needlessly multiplies
  latency. Use `pMap` with concurrency ≥ 2 for independent async items.
- **Materializing all results in memory for huge datasets**: a 10,000-item array of
  enriched objects can exhaust the 128 MB Worker memory limit. Chunk via Queue for
  large volumes.
- **Mixing CPU-bound work in tight loops with I/O**: synchronous transforms on each
  item add up. Pipeline CPU work as a separate synchronous pass after all I/O is done.
- **Ignoring partial failures**: `Promise.all` throws on first rejection; use
  `Promise.allSettled` or the `pMapSettled` helper to collect all errors before
  deciding whether to retry or return a partial response.

## Gotchas

- The 50-subrequest limit applies to external `fetch()` calls only. KV, D1, R2,
  Queue send, and service bindings have separate (higher) limits.
- `pMap` with `concurrency > items.length` is safe — it clamps implicitly because
  workers race for the shared index.
- CPU time (paid: 30s) does not pause during `await`; it accumulates. A pipeline
  that serially awaits many slow external calls can hit the CPU time limit even if
  each individual await is short.
- Result ordering: `pMap` guarantees results are in input order regardless of
  completion order — the index-based assignment (`results[i] = ...`) handles this.

## Verification

```typescript
// unit test for pMap
import { pMap } from "./pipeline";

it("preserves order under concurrent execution", async () => {
  const delays = [50, 10, 30, 5, 40]; // ms
  const results = await pMap(
    delays,
    (ms) => new Promise<number>((r) => setTimeout(() => r(ms), ms)),
    3
  );
  expect(results).toEqual([50, 10, 30, 5, 40]); // original order
});

it("respects concurrency cap", async () => {
  let inFlight = 0;
  let maxInFlight = 0;
  await pMap(
    Array.from({ length: 20 }, (_, i) => i),
    async () => {
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((r) => setTimeout(r, 5));
      inFlight--;
    },
    5
  );
  expect(maxInFlight).toBeLessThanOrEqual(5);
});
```

## Related

- `scatter-gather-parallel-workers.md` — parallel reads from multiple upstreams
- `bulkhead-pattern-workers-subrequests.md` — isolating subrequest budgets
- `pipes-and-filters-workers-pipeline.md` — functional composition of transforms
- `competing-consumers-workers-queues.md` — fan-out via Queue for high-volume batches
- `priority-queue-workers-queues.md` — prioritizing items within a processing queue

## Sources

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/allSettled
- https://developers.cloudflare.com/queues/configuration/javascript-apis/
