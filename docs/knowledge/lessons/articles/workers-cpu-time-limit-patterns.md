# Workers CPU Time Limit Patterns

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker that validates and transforms large JSON payloads consistently throws `Error: Worker exceeded CPU time limit` in production. A regex-based route matcher added for convenience causes P99 latency to exceed the 50 ms CPU budget on the free plan. A cryptographic batch operation that worked fine in local `wrangler dev` reliably times out in production because the local emulator does not enforce CPU limits the same way the runtime does.

## Context

Cloudflare Workers enforce a **CPU time limit**, not a wall-clock time limit. I/O (network requests, KV reads, D1 queries) does not count against the CPU budget — only time spent actually executing JavaScript. On the **free plan** the limit is 10 ms CPU per request (commonly cited as 50 ms in some docs; the actual enforced limit per billing tier should be verified in your dashboard). On **paid plans** (Workers Standard) the limit is 30 seconds of CPU per request. CPU time is measured as the sum of synchronous execution slices, excluding time spent `await`ing promises that are resolved by I/O.

## Solution

```typescript
import { Env } from './types';

// ─── Pattern 1: Measuring CPU time accurately ─────────────────────────────────
// performance.now() inside a Worker measures wall-clock time including I/O.
// To isolate CPU time, bracket synchronous sections and subtract known I/O wait.

export async function measureCpuHotspot(
  payload: unknown[]
): Promise<{ resultCount: number; cpuMs: number }> {
  const cpuStart = performance.now();
  // Pure CPU work — no await inside this block
  const results = payload
    .filter(item => typeof item === 'object' && item !== null)
    .map(item => JSON.stringify(item))
    .filter(s => s.length < 4096);
  const cpuEnd = performance.now();

  return { resultCount: results.length, cpuMs: cpuEnd - cpuStart };
}

// ─── Pattern 2: Offloading heavy computation to Queues ───────────────────────
// For CPU-intensive work that cannot be made faster, move it out of the
// request path entirely. The HTTP request enqueues the work and returns
// immediately. A queue consumer processes the payload asynchronously.

export async function handleTransformRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json() as { jobId: string; payload: unknown[] };

  // Enqueue instead of processing inline — returns in < 5 ms CPU
  await env.TRANSFORM_QUEUE.send({
    jobId: body.jobId,
    payload: body.payload,
    enqueuedAt: Date.now(),
  });

  return Response.json({ status: 'accepted', jobId: body.jobId }, { status: 202 });
}

// Queue consumer — has up to 15 minutes wall-clock, 30 s CPU per invocation
export async function processTransformBatch(
  batch: MessageBatch<{ jobId: string; payload: unknown[]; enqueuedAt: number }>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const { jobId, payload } = msg.body;
    try {
      // CPU-heavy work is now safe to perform here
      const transformed = expensiveTransform(payload);
      await env.RESULTS_KV.put(
        `job:${jobId}`,
        JSON.stringify({ status: 'done', result: transformed }),
        { expirationTtl: 3600 }
      );
      msg.ack();
    } catch (err) {
      msg.retry({ delaySeconds: 30 });
    }
  }
}

function expensiveTransform(payload: unknown[]): unknown[] {
  // Simulate expensive CPU work
  return payload.map(item => {
    if (typeof item !== 'object' || item === null) return item;
    // e.g. deep clone + schema normalisation
    return JSON.parse(JSON.stringify(item));
  });
}

// ─── Pattern 3: Streaming responses to avoid timeout ─────────────────────────
// A Worker that generates a large response synchronously may exceed CPU limits
// before the response is flushed. Use ReadableStream to interleave generation
// with I/O pauses, resetting the CPU slice budget.

export function streamLargeResponse(rows: AsyncIterable<unknown>): Response {
  const stream = new ReadableStream({
    async start(controller) {
      const encoder = new TextEncoder();
      controller.enqueue(encoder.encode('['));
      let first = true;
      for await (const row of rows) {
        // Each `for await` iteration yields to the event loop, allowing
        // the runtime to reset the CPU time slice measurement.
        if (!first) controller.enqueue(encoder.encode(','));
        controller.enqueue(encoder.encode(JSON.stringify(row)));
        first = false;
      }
      controller.enqueue(encoder.encode(']'));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: { 'Content-Type': 'application/json' },
  });
}

// ─── Pattern 4: Breaking CPU-bound loops with scheduler.wait(0) ──────────────
// For loops that cannot be made async by nature, yield to the event loop
// periodically using scheduler.wait(0). This resets the CPU time slice and
// prevents the 30 s aggregate CPU limit from being reached in a single spin.

export async function processBigArray(
  items: unknown[],
  chunkSize = 500
): Promise<unknown[]> {
  const results: unknown[] = [];

  for (let i = 0; i < items.length; i += chunkSize) {
    const chunk = items.slice(i, i + chunkSize);

    // Process chunk synchronously
    for (const item of chunk) {
      results.push(JSON.stringify(item).toUpperCase());
    }

    // Yield to event loop — I/O wait, no CPU charged during await
    // This also allows pending microtasks (e.g. KV read callbacks) to drain.
    if (i + chunkSize < items.length) {
      await scheduler.wait(0);
    }
  }

  return results;
}

// ─── Pattern 5: Durable Objects for longer compute ───────────────────────────
// Durable Objects run in a single-threaded isolate that is also subject to
// CPU limits, but the alarm handler can chain alarms to continue work across
// multiple invocations, each with a fresh CPU budget.

export class ComputeJobDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const job = await request.json() as { items: unknown[]; cursor: number };
    await this.state.storage.put('job', job);
    await this.state.storage.setAlarm(Date.now()); // run immediately
    return Response.json({ status: 'queued' });
  }

  async alarm(): Promise<void> {
    const job = await this.state.storage.get<{ items: unknown[]; cursor: number }>('job');
    if (!job) return;

    const CHUNK = 200;
    const end = Math.min(job.cursor + CHUNK, job.items.length);
    const chunk = job.items.slice(job.cursor, end);

    // Process one chunk within this alarm's CPU budget
    for (const item of chunk) {
      // ... process item ...
      void item;
    }

    job.cursor = end;
    if (job.cursor < job.items.length) {
      // More work remains — schedule next alarm immediately
      await this.state.storage.put('job', job);
      await this.state.storage.setAlarm(Date.now() + 50); // 50 ms gap
    } else {
      await this.state.storage.delete('job');
    }
  }
}

// ─── Pattern 6: Surprising CPU consumers ─────────────────────────────────────
// Operations that look "free" but consume meaningful CPU budget:

export async function surprisingCpuConsumers(env: Env): Promise<void> {
  // ❌ JSON.parse on a 1 MB payload: ~5–10 ms CPU
  // const data = JSON.parse(await response.text());  // avoid for large payloads

  // ✅ Stream-parse instead
  // const data = await response.json(); // still parses but avoids double-copy

  // ❌ String concatenation in a loop: O(n^2) for large strings
  let result = '';
  const parts = ['a', 'b', 'c'];
  // BAD: for (const p of parts) result += p;  // re-allocates on every iteration
  // GOOD:
  result = parts.join('');  // single allocation
  void result;

  // ❌ bcrypt / argon2 — these are intentionally CPU-heavy password hashing
  // algorithms. NEVER use them in a Worker request path. Use them in a
  // background Queue consumer or use a lighter KDF (PBKDF2 with 1000 iter).

  // ❌ Complex regex with catastrophic backtracking on user-supplied input:
  // const re = /^(a+)+$/;  // exponential on 'aaaaaaaaab'
  // re.test(userInput);    // can consume entire CPU budget

  // ✅ Use linear-time algorithms or pre-validate input length
  const safeInput = 'user-input'.slice(0, 128);
  const safeRe = /^[a-z0-9-]{1,64}$/;
  safeRe.test(safeInput);

  // ❌ SubtleCrypto RSA operations: 10–50 ms per sign/verify
  // For request-path token validation, use HMAC-SHA256 (< 0.5 ms) instead.
  const key = await crypto.subtle.generateKey(
    { name: 'HMAC', hash: 'SHA-256' },
    false, ['sign', 'verify']
  );
  const data = new TextEncoder().encode('hello');
  await crypto.subtle.sign('HMAC', key, data); // ~0.3 ms — acceptable
}
```

## Implementation Details

**Free vs paid CPU budgets.** The Workers free plan enforces 10 ms CPU per request (some documentation says 50 ms; check your account's actual limit in the Cloudflare dashboard under Workers & Pages → Limits). The Workers Standard paid plan raises this to 30 seconds per request. CPU time is the sum of synchronous JS execution, not wall-clock time.

**`scheduler.wait(0)` is not free.** Each `await scheduler.wait(0)` yields to the event loop and back, which takes roughly 0.05–0.1 ms of wall-clock time. In tight loops this can add up. Batch work into chunks of 100–500 items before yielding.

**`performance.now()` granularity.** Cloudflare rounds `performance.now()` to 0.1 ms precision to mitigate timing side-channels. This is fine for coarse CPU measurement but not for high-resolution benchmarking.

**Queue consumer CPU budget.** Queue consumers are separate Worker invocations and get their own full CPU budget. A batch of 100 messages can process in a single invocation if each message is cheap, or each message can get its own invocation by setting `max_batch_size = 1`.

## Anti-patterns

- **Inline cryptographic hashing of user-uploaded files.** SHA-256 over a 10 MB file takes ~20 ms CPU. For uploads, hash in a Queue consumer or use an R2 multipart upload event notification.
- **Chaining 10+ `fetch()` calls sequentially in CPU time.** While `fetch` awaits don't count as CPU time, the serialisation/deserialisation of each response body does. Parallelize with `Promise.all` where possible.
- **Using `JSON.stringify` on deeply nested objects with circular references.** Throws `TypeError` and consumes CPU before throwing. Detect circular references before serialising.
- **Importing a full NLP/ML library for trivial text matching.** Prefer a hardcoded lookup table or a simple regex over importing a 500 KB library whose initialisation alone consumes the cold-start CPU budget.

## Gotchas

- **`wrangler dev` does not enforce CPU limits.** Code that passes locally may throw `CPU time limit exceeded` in production. Always test under the real runtime with `wrangler dev --remote` or staging deployments.
- **CPU limit is per request, not per isolate.** Parallel requests in the same isolate each have their own CPU budget. Module-scope initialisers run against the first request's budget.
- **Tail Workers also consume CPU budget** from the originating request's account billing, but they run after the response is sent and do not block the request.
- **`waitUntil()` tasks have their own CPU budget** separate from the main request handler. Use `ctx.waitUntil(heavyWork())` to move post-response processing out of the request CPU window.

## Verification

```typescript
// Instrument CPU-sensitive handlers with timing assertions in staging:
async function assertCpuBudget<T>(
  name: string,
  fn: () => Promise<T>,
  maxMs: number
): Promise<T> {
  const start = performance.now();
  const result = await fn();
  const elapsed = performance.now() - start;
  if (elapsed > maxMs) {
    console.warn(`[CPU BUDGET] ${name} took ${elapsed.toFixed(1)} ms — limit ${maxMs} ms`);
  }
  return result;
}

// Usage in handler:
// const user = await assertCpuBudget('validateToken', () => validate(token), 5);
```

## Related

- `workers-cpu-slow-regex-budget-leak-incident.md`
- `workers-cpu-time-limit-exceeded-webhook-handler-incident.md`
- `workers-cpu-time-premature-optimization.md`
- `cloudflare-queues-vs-traditional-message-queues.md`
- `durable-objects-alarm-delivery-guarantee-lesson.md`

## Sources

- Cloudflare Workers — Limits: https://developers.cloudflare.com/workers/platform/limits/#cpu-time
- Cloudflare Queues — Consumer Workers: https://developers.cloudflare.com/queues/reference/consumer-concurrency/
- Durable Objects — Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Scheduler API (WHATWG): https://wicg.github.io/scheduling-apis/
- MDN — SubtleCrypto performance considerations: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
