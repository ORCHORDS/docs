# Batching AI Inference via Cloudflare Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Calling `env.AI.run()` per-request at high throughput hits per-minute neuron limits and increases tail latency. Batching inference — collecting N messages from a Queue, running them as a batch, then fanning results back to callers via D1 — amortises overhead and respects rate limits gracefully.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Bindings: `AI`, `DB` (D1), `INFERENCE_QUEUE` (Queue producer + consumer)
- Model: `@cf/meta/llama-3.1-8b-instruct`
- Pattern: HTTP handler enqueues job → Queue consumer batches up to 10 messages → `AI.run()` with array of prompts → writes results to D1 → caller polls D1 for result

---

## Section 1: Wrangler Configuration

```toml
# wrangler.toml
name = "ai-batch-inference"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[d1_databases]]
binding = "DB"
database_name = "inference_db"
database_id = "<your-d1-id>"

[[queues.producers]]
queue = "inference-queue"
binding = "INFERENCE_QUEUE"

[[queues.consumers]]
queue = "inference-queue"
max_batch_size = 10
max_batch_timeout = 5    # seconds to wait before processing a partial batch
max_retries = 3
dead_letter_queue = "inference-dlq"
```

## Section 2: D1 Schema for Job Tracking

```sql
-- migrations/001_inference_jobs.sql
CREATE TABLE IF NOT EXISTS inference_jobs (
  id          TEXT PRIMARY KEY,          -- UUID
  status      TEXT NOT NULL DEFAULT 'pending', -- pending | done | error
  prompt      TEXT NOT NULL,
  result      TEXT,
  error       TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_status ON inference_jobs(status);
```

```bash
npx wrangler d1 execute inference_db --remote --file migrations/001_inference_jobs.sql
```

## Section 3: HTTP Handler — Enqueue and Return Job ID

```typescript
// src/index.ts
import { Queue, D1Database } from '@cloudflare/workers-types';
import { processInferenceBatch } from './consumer';

export interface Env {
  AI: Ai;
  DB: D1Database;
  INFERENCE_QUEUE: Queue;
}

export default {
  // Enqueue a new inference job
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/infer' && request.method === 'POST') {
      const { prompt } = await request.json<{ prompt: string }>();
      if (!prompt?.trim()) return new Response('Missing prompt', { status: 400 });

      const jobId = crypto.randomUUID();

      // Write pending record
      await env.DB.prepare(
        'INSERT INTO inference_jobs (id, prompt, status) VALUES (?, ?, \'pending\')'
      )
        .bind(jobId, prompt)
        .run();

      // Enqueue
      await env.INFERENCE_QUEUE.send({ jobId, prompt });

      return Response.json({ jobId, status: 'pending' }, { status: 202 });
    }

    if (url.pathname.startsWith('/result/') && request.method === 'GET') {
      const jobId = url.pathname.replace('/result/', '');
      const row = await env.DB.prepare(
        'SELECT status, result, error FROM inference_jobs WHERE id = ?'
      )
        .bind(jobId)
        .first<{ status: string; result: string | null; error: string | null }>();

      if (!row) return new Response('Not found', { status: 404 });
      return Response.json(row);
    }

    return new Response('Not found', { status: 404 });
  },

  // Queue consumer — called automatically by the runtime
  async queue(batch: MessageBatch<{ jobId: string; prompt: string }>, env: Env): Promise<void> {
    await processInferenceBatch(batch, env);
  },
};
```

## Section 4: Queue Consumer — Batch AI Inference

```typescript
// src/consumer.ts
import { MessageBatch } from '@cloudflare/workers-types';
import { Env } from './index';

export async function processInferenceBatch(
  batch: MessageBatch<{ jobId: string; prompt: string }>,
  env: Env
): Promise<void> {
  const messages = batch.messages;

  // Build per-message prompts
  const inputs = messages.map((msg) => ({
    jobId: msg.body.jobId,
    messages: [
      { role: 'system' as const, content: 'You are a concise assistant.' },
      { role: 'user' as const, content: msg.body.prompt },
    ],
  }));

  // Run all prompts in parallel (Workers AI does not have a native batch endpoint
  // for chat; run concurrent promises bounded by batch size)
  const results = await Promise.allSettled(
    inputs.map(({ messages: msgs }) =>
      (env.AI as any).run('@cf/meta/llama-3.1-8b-instruct', {
        messages: msgs,
        max_tokens: 512,
        temperature: 0.7,
      })
    )
  );

  // Fan-out: write each result back to D1
  const now = new Date().toISOString();
  const writes = results.map((settled, i) => {
    const { jobId } = inputs[i];
    if (settled.status === 'fulfilled') {
      const text = (settled.value as { response?: string }).response ?? '';
      return env.DB.prepare(
        `UPDATE inference_jobs SET status='done', result=?, finished_at=? WHERE id=?`
      )
        .bind(text, now, jobId)
        .run();
    } else {
      const errMsg = settled.reason instanceof Error ? settled.reason.message : String(settled.reason);
      return env.DB.prepare(
        `UPDATE inference_jobs SET status='error', error=?, finished_at=? WHERE id=?`
      )
        .bind(errMsg, now, jobId)
        .run();
    }
  });

  await Promise.all(writes);

  // Acknowledge all messages
  batch.ackAll();
}
```

## Section 5: Polling Helper (Client Side)

```typescript
// client/poll.ts — example Node.js polling script
async function pollResult(baseUrl: string, jobId: string, maxWaitMs = 30_000): Promise<string> {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${baseUrl}/result/${jobId}`);
    const data = await res.json<{ status: string; result?: string; error?: string }>();
    if (data.status === 'done') return data.result ?? '';
    if (data.status === 'error') throw new Error(data.error ?? 'inference error');
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error('Timed out waiting for inference result');
}
```

## Anti-patterns

- Do NOT call `batch.ackAll()` before writing to D1 — if the D1 write fails the messages are gone and jobs stay `pending` forever.
- Do NOT set `max_batch_size` above the Workers AI concurrent request limit for your account tier.
- Do NOT store large prompt/result payloads (> 1 MB) in D1 TEXT columns — use R2 for large content and store only the R2 key in D1.
- Do NOT use `Promise.all` without `allSettled` — one failing inference should not prevent the others from being written.
- Do NOT forget a dead-letter queue — without it, poison messages cause infinite retries.

## Gotchas

- Queue consumers run in a separate Worker invocation from the HTTP handler; `env` bindings are the same but there is no shared in-memory state.
- `max_batch_timeout = 5` means the consumer may wait up to 5 seconds for more messages; latency-sensitive use-cases should lower this.
- `batch.ackAll()` vs `message.ack()` — `ackAll` is fine when you have already handled errors gracefully via `allSettled`.
- Workers AI does not expose a native batch-prompt API for chat models; parallel `Promise.allSettled` is the correct approach.
- D1 has a 10 MB per-row soft limit and a 100 MB per-database soft limit on the free tier.

## Verification

```bash
npx wrangler deploy

# Submit three jobs
for i in 1 2 3; do
  curl -s -X POST https://ai-batch-inference.<subdomain>.workers.dev/infer \
    -H 'Content-Type: application/json' \
    -d "{\"prompt\": \"Explain concept $i in one sentence.\"}" | jq .jobId
done

# Poll for result of first job (replace with real UUID)
JOB_ID="<uuid-from-above>"
for n in $(seq 1 10); do
  STATUS=$(curl -s https://ai-batch-inference.<subdomain>.workers.dev/result/$JOB_ID | jq -r .status)
  echo "$n: $STATUS"
  [ "$STATUS" = "done" ] && break
  sleep 1
done

# Inspect queue metrics
npx wrangler queues list
```

## Related

- `documentation/categories/ai-ml/workers-ai-function-calling-multi-step.md`
- `documentation/categories/ai-ml/workers-ai-prompt-caching-kv-cost-reduction.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/reference/batching-retries/
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/d1/
