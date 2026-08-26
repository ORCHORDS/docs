# Workers Memory 128MB Limit Exceeded OOM Postmortem

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A PDF-to-text extraction Worker began crashing with `Error: Worker exceeded memory limit` on documents larger than approximately 8 MB, causing 100% failure for the affected request class. The failures were non-deterministic in timing but correlated tightly with document size; small PDFs continued to succeed while all requests for large documents returned 500 errors with no retry recovery.

## Context

Cloudflare Workers run in a V8 isolate with a hard memory ceiling of 128 MB. This includes the Worker script itself, all in-memory data structures, and any wasm modules loaded at runtime. The extraction Worker used a WebAssembly PDF parsing library that decompressed the full document into a flat byte buffer before text extraction. For documents in the 8–20 MB compressed range, the in-memory representation after decompression could reach 150–350 MB, well above the isolate limit. The OOM kill is immediate and unrecoverable within the same invocation—the Worker is terminated and the request fails with no opportunity for graceful degradation.

## Timeline

- **11:00 UTC** — A batch import job submits 1,400 PDFs ranging from 200 KB to 18 MB to the extraction Worker via a Queue.
- **11:03 UTC** — First `Worker exceeded memory limit` errors appear in Logpush; error rate climbs to 34% of active Queue messages.
- **11:07 UTC** — Queue backlog grows as failed messages are retried; consumer scaling increases concurrency, amplifying memory pressure.
- **11:15 UTC** — On-call paged; initial hypothesis is a Queue message poison loop.
- **11:24 UTC** — Error message text identified as memory OOM, not a logic error. Correlation with document size confirmed via Logpush query.
- **11:35 UTC** — Queue consumer paused to stop retry amplification.
- **11:42 UTC** — Temporary mitigation: added a size gate that rejects documents >5 MB with a 413 status, routing them to a fallback path.
- **12:15 UTC** — Architecture decision made to move large-document processing to a Durable Object with chunked streaming to stay within the memory limit.
- **14:00 UTC** — Chunked streaming implementation deployed and tested; large documents re-queued successfully.
- **14:30 UTC** — Queue consumer re-enabled; all 1,400 documents processed without error.

## Root Cause

The WebAssembly PDF library's `parsePDF()` function loaded the entire document into a `Uint8Array` before beginning extraction. For a 12 MB compressed PDF, the decompressed in-memory representation was approximately 180 MB:

```typescript
// extraction-worker/src/index.ts — pre-incident (simplified)
import parsePdf from './vendor/pdf-parser.wasm';

export default {
  async queue(batch: MessageBatch<QueueMessage>, env: Env) {
    for (const msg of batch.messages) {
      const { objectKey } = msg.body;

      // Fetch the full PDF from R2 — fine for small files
      const object = await env.R2_DOCS.get(objectKey);
      if (!object) { msg.ack(); continue; }

      // arrayBuffer() loads the entire file into memory
      const bytes = new Uint8Array(await object.arrayBuffer()); // up to 18 MB compressed

      // parsePdf decompresses the entire document in-wasm memory
      // For a 12 MB PDF, wasm heap can reach 150-200 MB
      const text = await parsePdf(bytes); // OOM thrown here for large docs

      await env.KV_EXTRACTED.put(objectKey, text);
      msg.ack();
    }
  },
};
```

The `parsePdf` wasm module held a linear wasm heap that grew proportionally to the decompressed document size. V8's 128 MB isolate limit counts both the JavaScript heap and the wasm linear memory—so a 20 MB wasm heap allocation in `parsePdf` plus normal Worker runtime overhead pushed total memory over the limit. There was no per-message size check, no streaming extraction path, and no monitoring for memory usage trends.

## Fix Applied

**Immediate mitigation** (11:42 UTC): size gate to reject large documents and route them manually:

```typescript
const MAX_SAFE_PDF_BYTES = 5 * 1024 * 1024; // 5 MB

const object = await env.R2_DOCS.get(objectKey);
if (object && object.size > MAX_SAFE_PDF_BYTES) {
  // Publish to a separate large-doc queue for Durable Object processing
  await env.LARGE_DOC_QUEUE.send({ objectKey, size: object.size });
  msg.ack();
  continue;
}
```

**Architectural fix** (deployed 14:00 UTC): chunked streaming via a Durable Object that processes the PDF page-by-page, keeping peak memory below 40 MB:

```typescript
// large-doc-extractor/src/durable-object.ts

export class LargeDocExtractor implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const { objectKey } = await request.json<{ objectKey: string }>();

    const object = await this.env.R2_DOCS.get(objectKey);
    if (!object) return new Response('Not found', { status: 404 });

    // Stream the R2 object body through a TransformStream
    // to avoid loading the whole PDF into memory at once
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();

    const extracted: string[] = [];
    const reader = object.body.getReader();
    const pageParser = new IncrementalPdfParser(); // processes page-at-a-time

    let done = false;
    while (!done) {
      const { value, done: readerDone } = await reader.read();
      done = readerDone;
      if (value) {
        // Feed chunk to incremental parser; yields completed pages
        for (const page of pageParser.feed(value)) {
          extracted.push(page.text);
          // Immediately discard parsed page data from wasm heap
          page.free();
        }
      }
    }

    const fullText = extracted.join('\n');
    await this.env.KV_EXTRACTED.put(objectKey, fullText);

    return Response.json({ ok: true, pages: extracted.length });
  }
}
```

```typescript
// Queue consumer routes large docs to the Durable Object
const stub = env.LARGE_DOC_EXTRACTOR.get(
  env.LARGE_DOC_EXTRACTOR.idFromName(objectKey)
);
await stub.fetch(new Request('https://do/extract', {
  method: 'POST',
  body: JSON.stringify({ objectKey }),
}));
```

## What We Learned

1. **Workers have a hard 128 MB memory limit that includes wasm linear memory.** WebAssembly modules that decompress or expand data structures can consume far more memory than the source file size implies; always benchmark wasm library memory usage against the largest expected input.
2. **OOM kills are non-recoverable within the same invocation.** Unlike CPU timeout errors, there is no way to catch or gracefully handle an OOM—the isolate is terminated. Defensive input size checks before memory-intensive operations are the only protection.
3. **Queue consumer retry amplification worsens memory pressure under OOM conditions.** When messages fail they are retried immediately, which can saturate all available consumer concurrency with OOM-bound messages.
4. **Streaming is the correct pattern for large binary payloads.** R2 objects can be streamed via `ReadableStream`; passing the full `arrayBuffer()` to a wasm module is an anti-pattern for files above ~2 MB.
5. **Durable Objects are a natural fit for stateful, long-running document processing** that exceeds what a stateless Worker invocation can hold in memory.

## Prevention

- **Input size gate**: every Worker that handles binary payloads must have an early exit if `object.size > MAX_SAFE_BYTES`, with `MAX_SAFE_BYTES` calculated as `(128 MB - baseline_worker_memory) / expansion_factor`.
- **Memory profiling in CI**: run the Worker against a set of large test documents using Miniflare with memory tracking enabled; fail the build if peak memory exceeds 100 MB.
- **Analytics Engine memory metric**: add a `performance.memory` reading (where available in the Workers runtime) to every Queue consumer invocation and alert when p99 exceeds 90 MB.
- **Queue poison message circuit breaker**: configure maximum retries per message (`maxRetries: 2`) and a dead-letter queue so OOM-bound messages stop retrying after 3 attempts.

```toml
# wrangler.toml
[[queues.consumers]]
queue = "doc-extraction"
max_retries = 2
dead_letter_queue = "doc-extraction-dlq"
```

- **Size-tiered routing at enqueue time**: classify documents by size at upload time and enqueue to separate queues (`doc-extraction-small`, `doc-extraction-large`) with different consumer Workers.

## Anti-patterns

- Calling `.arrayBuffer()` on an R2 object of unknown or unbounded size before passing it to a wasm module.
- Assuming wasm linear memory is free from the Worker isolate's memory budget—it is not.
- Processing all document sizes through a single Worker with no per-size code path.
- Relying on Queue retry to recover from OOM failures without a maximum retry cap or dead-letter queue.
- Not benchmarking wasm library memory usage against maximum expected input sizes before production deployment.

## Gotchas

- The `object.size` property on an `R2Object` is available before calling `.arrayBuffer()` or `.body`—always check it first.
- `performance.memory` is not guaranteed to be available in all Workers runtime versions; wrap access in a `try/catch` and emit a fallback metric of `-1` when unavailable.
- Durable Objects also have a 128 MB memory limit per instance; chunked streaming must ensure peak in-flight memory stays below this limit even in the DO.
- `TransformStream` backpressure is not automatically applied when a wasm consumer is slower than the R2 stream—implement explicit flow control with `reader.read()` in a loop rather than `pipeTo()` if the wasm module is synchronous.
- The V8 garbage collector does not immediately reclaim memory released by wasm modules; `page.free()` on the wasm side is necessary to explicitly release wasm linear memory between pages.

## Verification

1. Replay the original 18 MB PDF through the new chunked streaming path in staging; confirm no `Worker exceeded memory limit` error and that the Durable Object reports peak memory below 50 MB.
2. Re-process the 1,400-document batch via the size-tiered queues; confirm all documents complete successfully with zero messages in the dead-letter queue.
3. Check Logpush for `Worker exceeded memory limit` errors on the extraction Workers for 24 hours post-fix; confirm zero occurrences.
4. Verify Analytics Engine shows p99 memory below 60 MB for both the small-doc Worker and the Durable Object extraction path.

## Related

- [Durable Objects Storage Quota Limit Incident](durable-objects-storage-quota-limit-incident.md)
- [D1 Batch Size Limit Exceeded Postmortem](d1-batch-size-limit-exceeded-postmortem.md)
- [Queues Consumer Scaling Backpressure Lesson](queues-consumer-scaling-backpressure-lesson.md)
- [Queues Consumer Visibility Timeout Retry Storm Postmortem](queues-consumer-visibility-timeout-retry-storm-postmortem.md)
- [R2 Multipart Upload Size Limit Lesson](r2-multipart-upload-size-limit-lesson.md)

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#memory
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#r2object-properties
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
