# Workers Unbound CPU Time Management

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your Worker does synchronous cryptographic work, LLM token streaming, or large-batch data transformation. The standard Workers plan's 10 ms CPU limit kills it before the task finishes. You move to Workers Unbound (or Workers Paid with the Unbound compute option) and discover the billing model is CPU-millisecond-based, not wall-clock-based, which means the cost is driven by how much time the JavaScript engine is actually executing — not waiting on I/O. Understanding how to profile, measure, and cap CPU usage is essential to avoiding runaway bills and hitting duration limits correctly.

---

## Context

### Standard vs. Unbound CPU limits

| Plan | Max CPU time | Max wall-clock duration | Billing unit |
|------|-------------|------------------------|--------------|
| Workers Free | 10 ms | 30 s (with `waitUntil`) | Requests (50K/day free) |
| Workers Paid (Standard) | 30 ms | 30 s (subrequest), 30 min (Cron) | Requests |
| Workers Unbound | No hard CPU cap* | 15 min (Fetch), 15 min (Cron), 30 min DO | CPU-milliseconds |

*Unbound workers still have a **CPU time limit of 30 000 ms** (30 CPU-seconds) per invocation as of 2025 for HTTP handlers. Cron Triggers and Queue consumers have a wall-clock timeout of 15 minutes. The key difference is that I/O wait time does not count toward the CPU budget.

### How CPU time is measured

CPU time = time the JS engine is executing synchronous JavaScript, NOT including:
- Time spent waiting for `await fetch(…)`
- Time spent waiting for `await env.KV.get(…)` or any other async I/O
- Time spent in the Cloudflare runtime's own code paths between your JS frames

A Worker that does `await fetch(url)` and waits 2 seconds for the upstream server uses ≈0 CPU milliseconds during that wait. Only the time your code spends actually running counts.

---

## Measuring CPU Time in Your Worker

Use `Date.now()` around synchronous work, or better, use the `performance.now()` Web API which measures wall-clock time in the Worker's execution context. For CPU-specific measurement, rely on the `cf-ray` and Cloudflare's Workers Trace:

```typescript
// workers/cpu-profiler.ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = performance.now();

    // --- CPU-intensive work ---
    const result = await doWork(request);
    // -------------------------

    const elapsed = performance.now() - start;
    console.log(`Wall-clock: ${elapsed.toFixed(2)}ms`);

    return new Response(JSON.stringify(result), {
      headers: {
        "Content-Type": "application/json",
        "X-Worker-Duration-Ms": elapsed.toFixed(2),
      },
    });
  },
};

async function doWork(req: Request): Promise<unknown> {
  // Simulate a mix of CPU and I/O
  const cpuStart = performance.now();

  // I/O: does NOT count toward CPU time
  const upstream = await fetch("https://api.example.com/data");
  const data = await upstream.json();

  const cpuBeforeProcess = performance.now();

  // CPU: synchronous transform — DOES count
  const processed = JSON.parse(JSON.stringify(data)); // deep clone (toy example)

  const cpuEnd = performance.now();
  console.log(`Processing CPU time ≈ ${(cpuEnd - cpuBeforeProcess).toFixed(2)}ms`);

  return processed;
}
```

### Reading actual CPU time from the analytics

Workers Analytics Engine and Cloudflare Logpush emit the `cpuTime` field per invocation (in milliseconds). Set up a Logpush job to forward to R2 or your SIEM:

```json
{
  "name": "workers-cpu-metrics",
  "destination_conf": "r2://my-logs-bucket/workers/{DATE}?account-id=...&access-key-id=...&secret-access-key=...",
  "dataset": "workers_trace_events",
  "logpull_options": "fields=CpuTimeUs,Outcome,ScriptName,EventTimestampMs,WallTimeUs"
}
```

`CpuTimeUs` is in microseconds. Divide by 1 000 to get milliseconds for comparison against the Unbound billing unit.

---

## Optimising CPU-Heavy Patterns

### Pattern 1: Move I/O before CPU work

Always fetch all remote data before starting CPU work so the I/O wait does not hold up your CPU clock.

```typescript
// BAD: interleaves I/O and CPU
async function processItems(ids: string[]): Promise<unknown[]> {
  const results = [];
  for (const id of ids) {
    const raw = await fetch(`https://api.example.com/${id}`);  // I/O
    const data = await raw.json();
    results.push(expensiveTransform(data));  // CPU — but serial with I/O
  }
  return results;
}

// GOOD: fan-out I/O, then process in bulk
async function processItemsParallel(ids: string[]): Promise<unknown[]> {
  // All fetches run concurrently — I/O waits overlap
  const raws = await Promise.all(
    ids.map((id) => fetch(`https://api.example.com/${id}`).then((r) => r.json()))
  );
  // CPU runs once, uninterrupted, after all I/O completes
  return raws.map(expensiveTransform);
}
```

### Pattern 2: Stream processing to avoid JSON.parse of giant payloads

`JSON.parse` of a 10 MB string takes ~50–100 CPU ms. Use streaming parsers or chunked processing:

```typescript
import { JSONParser } from "@streamparser/json-whatwg";  // add to package.json

async function streamLargeJson(url: string): Promise<void> {
  const response = await fetch(url);
  const parser = new JSONParser({ paths: ["$.items.*"] });

  parser.onValue = ({ value }) => {
    // Process each item as it arrives — CPU spread across many small chunks
    processItem(value as Record<string, unknown>);
  };

  const writer = parser.writable.getWriter();
  const reader = response.body!.getReader();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    await writer.write(value);  // Each chunk: I/O wait, then small CPU burst
  }
  await writer.close();
}
```

### Pattern 3: Cryptographic work

Web Crypto API operations (`crypto.subtle.*`) are synchronous in their CPU cost but are implemented as native code — they use far less CPU time than equivalent JavaScript implementations.

```typescript
// Use Web Crypto instead of a pure-JS library for hashing/signing
async function hashMany(payloads: string[]): Promise<string[]> {
  const encoder = new TextEncoder();
  return Promise.all(
    payloads.map(async (p) => {
      const digest = await crypto.subtle.digest("SHA-256", encoder.encode(p));
      return Array.from(new Uint8Array(digest))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
    })
  );
}
```

---

## Handling the 30-Second CPU Limit

If a single handler risks exceeding 30 CPU-seconds, break work into segments using Durable Objects or Queues:

```typescript
// workers/chunked-processor.ts
export default {
  async queue(batch: MessageBatch<{ id: string }>, env: Env): Promise<void> {
    const CHUNK_SIZE = 100;  // tune based on per-item CPU cost

    for (const msg of batch.messages) {
      const item = msg.body;
      const cpuStart = performance.now();

      await processOne(item.id, env);

      const elapsed = performance.now() - cpuStart;

      // If we're approaching the limit, ack and let the next batch handle the rest
      // (Queues retry un-acked messages automatically)
      if (elapsed > 25_000) {  // 25 s wall-clock as safety margin
        console.warn(`CPU budget approaching — stopping at item ${item.id}`);
        msg.ack();
        // Remaining messages in batch will retry in next delivery
        return;
      }

      msg.ack();
    }
  },
};
```

---

## Billing and Cost Estimation

Workers Unbound billing (as of 2025):

| Resource | Free included | Overage rate |
|----------|--------------|-------------|
| Requests | 1M/month | $0.15 per million |
| CPU time | 400 000 CPU-ms/month | $0.02 per 1 000 CPU-ms |
| Duration (wall-clock) | Unlimited | Not billed separately |

Estimating monthly cost for a CPU-heavy worker:

```typescript
// scripts/estimate-cost.ts
const requestsPerMonth = 500_000;
const avgCpuMsPerRequest = 150; // measure with Logpush

const totalCpuMs = requestsPerMonth * avgCpuMsPerRequest;
const freeCpuMs = 400_000;
const billableCpuMs = Math.max(0, totalCpuMs - freeCpuMs);

const cpuCost = (billableCpuMs / 1_000) * 0.02;
const requestCost = Math.max(0, (requestsPerMonth - 1_000_000) / 1_000_000) * 0.15;

console.log(`CPU cost: $${cpuCost.toFixed(2)}`);
console.log(`Request cost: $${requestCost.toFixed(2)}`);
console.log(`Total: $${(cpuCost + requestCost).toFixed(2)}`);
```

Set a **Spending Alert** in the Cloudflare dashboard (Account → Billing → Spending Alerts) to receive an email when projected monthly spend exceeds a threshold.

---

## Anti-patterns

- **Using `while(true)` polling loops.** Spinning in a tight loop burns CPU time without making progress. Always use `await`-based sleep (`new Promise(r => setTimeout(r, ms))`) or event-driven patterns.
- **Importing heavy npm packages for tasks Web APIs cover.** `moment`, `lodash`, `uuid/v4`, `js-sha256`, and similar packages add parse overhead and CPU time every cold start. Use native `Temporal`, `Array.from`, `crypto.randomUUID()`, and `crypto.subtle` instead.
- **Parsing the same large JSON more than once.** Cache the parsed object in module scope if the data does not change between requests. Module-scope variables persist for the lifetime of the isolate (multiple requests on the same instance).
- **Running Workers Unbound for trivially short tasks.** If your P99 CPU time is 2 ms, Unbound's overhead billing is worse than Standard. Use Unbound only when you reliably exceed the 30 ms Standard limit.

---

## Gotchas

1. **`setTimeout` does not count as I/O wait in all implementations.** In Workers, `setTimeout` IS I/O (it suspends the isolate). CPU time pauses during a `setTimeout`. But spinning with `Date.now()` comparisons (busy-wait) does count as CPU.
2. **WebAssembly execution counts as CPU time.** If you use a Wasm module (e.g., for image processing or parsing), its execution is counted against your CPU budget.
3. **The 30-second CPU cap is a hard kill.** When a Worker exceeds 30 CPU-seconds, it receives a `cpu exceeded` error and the request is terminated — there is no grace period for cleanup. Use `ctx.waitUntil` to push cleanup to post-response if you're near the limit.
4. **Cold start CPU is not billed.** The time it takes for Cloudflare to instantiate your Worker isolate and execute module-level code is not charged as CPU time to your account.
5. **Workers AI inference is NOT CPU time.** Calls to `env.AI.run(...)` are remote — the AI computation happens on Cloudflare's GPU infrastructure, not your Worker isolate. You pay for AI tokens/neurons separately.

---

## Verification

```bash
# View recent CPU usage in Workers analytics
npx wrangler tail --format=json my-worker | jq 'select(.outcome=="ok") | .cpuTime'

# Check usage in the dashboard
# Cloudflare Dashboard → Workers & Pages → [Worker] → Analytics → CPU Time

# Logpush verification: check fields available
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/logpush/datasets/workers_trace_events/fields" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result | keys'
```

---

## Related

- `workers-resource-limits.md` — subrequest limits, memory limits, and other per-request caps
- `workers-configurable-subrequest-budget.md` — controlling sub-fetch cost
- `workers-waituntil-shared-post-response-budget.md` — post-response background work
- `workers-best-practices.md` — general Worker performance patterns
- `workers-logpush.md` — exporting trace events for CPU analysis
- `durable-objects-best-practices.md` — offloading long-running work to DOs

---

## Sources

- Workers Pricing: https://developers.cloudflare.com/workers/platform/pricing/
- Workers Limits: https://developers.cloudflare.com/workers/platform/limits/
- Workers Unbound: https://developers.cloudflare.com/workers/configuration/compatibility-dates/#workers-unbound
- Logpush Workers Trace Events: https://developers.cloudflare.com/logs/reference/log-fields/account/workers_trace_events/
