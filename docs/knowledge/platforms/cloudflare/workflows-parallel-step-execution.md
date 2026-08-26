# Cloudflare Workflows Parallel Step Execution

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You have a Cloudflare Workflow that needs to call multiple independent APIs, run several
sub-tasks, or fan out to different services at the same time — but sequential `step.do()`
calls add latency equal to the sum of all step durations. You want true parallel execution
with automatic retry and durable state, not fire-and-forget `waitUntil` hacks.

## Context

Cloudflare Workflows (GA 2025) model execution as a series of durable, replayed steps.
Each `step.do()` is checkpointed after it resolves. To run steps in parallel you wrap
multiple `step.do()` calls in `Promise.all()` — Workflows replays them correctly from
the checkpoint because each step is identified by its name, not its position.

Key constraints:
- Step names must be unique within a Workflow instance. Duplicate names cause replay errors.
- `Promise.all` inside a Workflow does launch parallel HTTP calls; the Workflow engine
  checkpoints the batch as a unit once all promises resolve.
- Each parallel step still counts toward the per-instance CPU and wall-clock budget.
- Workflows are available on Workers Paid and above; the free tier has no Workflows access.

---

## 1. Basic Parallel Fan-Out

```typescript
import { WorkflowEntrypoint, WorkflowStep, WorkflowEvent } from 'cloudflare:workers';

interface Env {
  MY_WORKFLOW: Workflow;
}

type Params = { orderId: string };

export class OrderWorkflow extends WorkflowEntrypoint<Env, Params> {
  async run(event: WorkflowEvent<Params>, step: WorkflowStep) {
    const { orderId } = event.payload;

    // Run three independent enrichment steps in parallel
    const [inventory, pricing, shipping] = await Promise.all([
      step.do('fetch-inventory', async () => {
        const res = await fetch(`https://api.example.com/inventory/${orderId}`);
        return res.json<{ available: number }>();
      }),
      step.do('fetch-pricing', async () => {
        const res = await fetch(`https://api.example.com/pricing/${orderId}`);
        return res.json<{ total: number }>();
      }),
      step.do('fetch-shipping', async () => {
        const res = await fetch(`https://api.example.com/shipping/${orderId}`);
        return res.json<{ eta: string }>();
      }),
    ]);

    // Sequential step that depends on all parallel results
    await step.do('create-order-summary', async () => {
      return { orderId, inventory, pricing, shipping };
    });
  }
}
```

---

## 2. Dynamic Parallel Steps with Unique Names

When the number of parallel tasks is dynamic (e.g., processing an array of items), generate
unique step names per item to avoid replay collisions.

```typescript
export class BatchWorkflow extends WorkflowEntrypoint<Env, { items: string[] }> {
  async run(event: WorkflowEvent<{ items: string[] }>, step: WorkflowStep) {
    const { items } = event.payload;

    // Generate unique step names per item — critical for correct replay
    const results = await Promise.all(
      items.map((item, idx) =>
        step.do(`process-item-${idx}-${item}`, async () => {
          const res = await fetch(`https://api.example.com/process`, {
            method: 'POST',
            body: JSON.stringify({ item }),
            headers: { 'Content-Type': 'application/json' },
          });
          if (!res.ok) throw new Error(`Failed for ${item}: ${res.status}`);
          return res.json<{ result: string }>();
        })
      )
    );

    await step.do('aggregate-results', async () => {
      return results.map((r, i) => ({ item: items[i], ...r }));
    });
  }
}
```

---

## 3. Parallel Stages with a Sequential Gate

Model a pipeline where two parallel phases each complete before triggering the next
sequential stage. Use nested `Promise.all` for multi-phase workflows.

```typescript
export class PipelineWorkflow extends WorkflowEntrypoint<Env, { jobId: string }> {
  async run(event: WorkflowEvent<{ jobId: string }>, step: WorkflowStep) {
    const { jobId } = event.payload;

    // Phase 1: parallel data ingestion
    const [rawA, rawB] = await Promise.all([
      step.do('ingest-source-a', async () => fetchSource('A', jobId)),
      step.do('ingest-source-b', async () => fetchSource('B', jobId)),
    ]);

    // Sequential gate: validate before proceeding
    const validated = await step.do('validate-inputs', async () => {
      if (!rawA.records || !rawB.records) throw new Error('Missing records');
      return { a: rawA.records, b: rawB.records };
    });

    // Phase 2: parallel transformation
    const [transformedA, transformedB] = await Promise.all([
      step.do('transform-a', async () => transform(validated.a)),
      step.do('transform-b', async () => transform(validated.b)),
    ]);

    await step.do('merge-and-store', async () => {
      return [...transformedA, ...transformedB];
    });
  }
}

async function fetchSource(src: string, jobId: string) {
  const res = await fetch(`https://data.example.com/source/${src}?job=${jobId}`);
  return res.json<{ records: unknown[] }>();
}

function transform(records: unknown[]) {
  return records; // real logic here
}
```

---

## 4. Handling Partial Failures with Promise.allSettled

When you want some steps to fail without aborting the whole workflow, use
`Promise.allSettled` and inspect results manually.

```typescript
export class ResilientWorkflow extends WorkflowEntrypoint<Env, { id: string }> {
  async run(event: WorkflowEvent<{ id: string }>, step: WorkflowStep) {
    const { id } = event.payload;

    const outcomes = await Promise.allSettled([
      step.do('notify-email', async () => sendEmail(id)),
      step.do('notify-sms', async () => sendSms(id)),
      step.do('notify-webhook', async () => callWebhook(id)),
    ]);

    const failures = outcomes
      .map((o, i) => ({ i, o }))
      .filter(({ o }) => o.status === 'rejected');

    if (failures.length > 0) {
      await step.do('log-partial-failures', async () => ({
        failed: failures.map(({ i, o }) => ({
          index: i,
          reason: (o as PromiseRejectedResult).reason?.message,
        })),
      }));
    }
  }
}

async function sendEmail(id: string) { /* ... */ }
async function sendSms(id: string) { /* ... */ }
async function callWebhook(id: string) { /* ... */ }
```

---

## 5. Concurrency Limiting for Large Fan-Outs

Launching hundreds of parallel steps at once can hit subrequest limits (currently 1000
subrequests per Worker invocation). Batch into chunks.

```typescript
async function parallelChunked<T>(
  items: T[],
  chunkSize: number,
  step: WorkflowStep,
  fn: (item: T, idx: number) => Promise<unknown>
) {
  const results: unknown[] = [];
  for (let i = 0; i < items.length; i += chunkSize) {
    const chunk = items.slice(i, i + chunkSize);
    const chunkResults = await Promise.all(
      chunk.map((item, j) => fn(item, i + j))
    );
    results.push(...chunkResults);
  }
  return results;
}

export class ChunkedWorkflow extends WorkflowEntrypoint<Env, { urls: string[] }> {
  async run(event: WorkflowEvent<{ urls: string[] }>, step: WorkflowStep) {
    const { urls } = event.payload;

    const results = await parallelChunked(urls, 50, step, (url, idx) =>
      step.do(`fetch-url-${idx}`, async () => {
        const res = await fetch(url);
        return { url, status: res.status };
      })
    );

    await step.do('store-results', async () => results);
  }
}
```

---

## Anti-Patterns

- **Reusing step names across parallel branches.** `step.do('fetch')` called twice in the
  same `Promise.all` will collide on replay. Always make names unique.
- **Spawning unbounded parallel steps on large arrays.** Hitting the subrequest cap
  (1000/invocation) causes a runtime error. Chunk your fan-outs.
- **Putting non-deterministic logic outside steps.** `Math.random()` or `Date.now()` called
  outside a `step.do()` produces different values on replay, causing split-brain state.
- **Using `waitUntil` instead of steps for parallel work.** `waitUntil` is not durable;
  if the Worker is evicted mid-execution the work is lost silently.

---

## Gotchas

- `Promise.all` wrapping `step.do` calls works, but `Promise.race` is not reliably durable —
  Workflows will still wait for all steps to settle before checkpointing.
- Step return values must be JSON-serialisable. Returning a `Response` object from a step
  silently serialises to `{}`.
- Workflow instance IDs are user-supplied strings; choose IDs carefully for idempotency.
  Re-triggering the same ID resumes the existing run, it does not start a new one.
- `step.sleep()` inside a parallel branch pauses only that branch; other branches continue
  normally. Total wall clock is bounded by the longest branch.

---

## Verification

```bash
# Trigger a workflow instance via Wrangler
wrangler workflows trigger MY_WORKFLOW --payload '{"orderId":"test-123"}'

# Inspect instance status
wrangler workflows instances describe MY_WORKFLOW <instance-id>

# Stream logs during execution
wrangler tail --format pretty
```

Expected: instance status transitions `queued → running → complete`. Each parallel step
shows a distinct name with its own `started_at` / `ended_at` timestamps overlapping in time.

---

## Related

- `cloudflare-workflows-human-in-the-loop-approval.md`
- `workflows-best-practices.md`
- `workers-rpc-service-binding-patterns.md`
- `cloudflare-queues-dead-letter-dlq.md`

---

## Sources

- https://developers.cloudflare.com/workflows/
- https://developers.cloudflare.com/workflows/reference/step-do/
- https://developers.cloudflare.com/workers/platform/limits/#subrequests
