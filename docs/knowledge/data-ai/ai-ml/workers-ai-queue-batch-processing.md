# Workers AI Async Batch Processing with Cloudflare Queues

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You need to run LLM inference over thousands of documents—product descriptions,
support tickets, transcripts—without blocking HTTP responses or hitting the per-Worker
CPU-time limit. Synchronous, request-driven inference caps throughput to one document
per HTTP round-trip and fails with timeout errors on large batches. You need a
fire-and-forget pipeline where producers enqueue work, consumers process it at a
controlled rate, and results land in durable storage.

## Context

Cloudflare Queues is a message-queue service with at-least-once delivery, batching,
dead-letter queues (DLQ), and native Workers integration. Pairing it with Workers AI
lets you:
- Decouple HTTP ingestion from inference compute.
- Control concurrency: one consumer Worker processes up to `max_batch_size` messages
  in parallel.
- Handle back-pressure: the Queue retries failed messages automatically with
  configurable delay.
- Pipe results to D1, R2, or downstream queues.

Throughput ceiling: Workers AI `@cf/meta/llama-3.1-8b-instruct` sustains roughly
20–50 tokens/s per invocation on the free tier and higher on the paid tier. At
`max_batch_size = 5` and 256 output tokens each, a batch takes ≈ 5–15 s—well within
the 15-minute consumer time limit.

## Queue and Binding Configuration

```jsonc
// wrangler.jsonc
{
  "name": "batch-inference",
  "compatibility_date": "2025-09-01",
  "ai": { "binding": "AI" },
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "inference-results",
      "database_id": "your-d1-db-id"
    }
  ],
  "queues": {
    "producers": [
      { "binding": "INFERENCE_QUEUE", "queue": "ai-inference-tasks" }
    ],
    "consumers": [
      {
        "queue": "ai-inference-tasks",
        "max_batch_size": 5,
        "max_batch_timeout": 10,
        "max_retries": 3,
        "dead_letter_queue": "ai-inference-dlq"
      }
    ]
  }
}
```

Create the queues:

```bash
wrangler queues create ai-inference-tasks
wrangler queues create ai-inference-dlq
```

D1 schema for results:

```sql
-- migrations/0001_inference_results.sql
CREATE TABLE IF NOT EXISTS inference_results (
  id          TEXT PRIMARY KEY,
  input_text  TEXT NOT NULL,
  output_text TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',  -- pending | done | failed
  error       TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  finished_at INTEGER
);
```

## Producer: Enqueue Inference Tasks

```typescript
// src/producer.ts
export interface Env {
  INFERENCE_QUEUE: Queue<InferenceTask>;
  DB: D1Database;
}

export interface InferenceTask {
  taskId: string;
  inputText: string;
  prompt: string;
  maxTokens: number;
}

import { randomUUID } from "node:crypto";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST required", { status: 405 });
    }

    const body = (await request.json()) as { texts: string[]; prompt: string };
    const { texts, prompt } = body;

    if (!Array.isArray(texts) || texts.length === 0) {
      return new Response("texts array is required", { status: 400 });
    }

    const tasks: InferenceTask[] = texts.map((inputText) => ({
      taskId:    randomUUID(),
      inputText,
      prompt:    prompt ?? "Summarise the following text in one sentence:",
      maxTokens: 128,
    }));

    // Write pending rows to D1 before enqueuing
    const placeholders = tasks.map(() => "(?, ?, 'pending', ?)").join(",");
    const values = tasks.flatMap((t) => [t.taskId, t.inputText, Date.now()]);
    await env.DB.prepare(
      `INSERT INTO inference_results (id, input_text, status, created_at) VALUES ${placeholders}`,
    ).bind(...values).run();

    // Batch-send to the queue (up to 100 messages per sendBatch call)
    const CHUNK = 100;
    for (let i = 0; i < tasks.length; i += CHUNK) {
      const chunk = tasks.slice(i, i + CHUNK);
      await env.INFERENCE_QUEUE.sendBatch(
        chunk.map((t) => ({ body: t, contentType: "json" })),
      );
    }

    return Response.json({
      enqueued: tasks.length,
      taskIds: tasks.map((t) => t.taskId),
    });
  },
};
```

## Consumer: Parallel Batch Inference

```typescript
// src/consumer.ts
import type { InferenceTask } from "./producer";

export interface Env {
  AI: Ai;
  DB: D1Database;
}

/** Run inference on a single task. Returns null on error. */
async function runInference(
  task: InferenceTask,
  ai: Ai,
): Promise<{ taskId: string; output: string } | { taskId: string; error: string }> {
  try {
    const result = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: [
        { role: "system", content: task.prompt },
        { role: "user",   content: task.inputText },
      ],
      max_tokens: task.maxTokens,
      temperature: 0.3,
    });

    const output =
      typeof result === "object" && "response" in result
        ? (result as { response: string }).response
        : "";

    return { taskId: task.taskId, output };
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return { taskId: task.taskId, error };
  }
}

export default {
  /** queue() is called with a batch of up to max_batch_size messages. */
  async queue(
    batch: MessageBatch<InferenceTask>,
    env: Env,
  ): Promise<void> {
    // Run all tasks in the batch concurrently
    const outcomes = await Promise.all(
      batch.messages.map((msg) => runInference(msg.body, env.AI)),
    );

    const now = Date.now();

    // Write results to D1 in one statement
    for (const msg of batch.messages) {
      const outcome = outcomes.find((o) => o.taskId === msg.body.taskId);
      if (!outcome) continue;

      if ("error" in outcome) {
        await env.DB.prepare(
          `UPDATE inference_results
           SET status = 'failed', error = ?, finished_at = ?
           WHERE id = ?`,
        ).bind(outcome.error, now, outcome.taskId).run();

        // Retry: ack=false causes the Queue to retry this specific message.
        // For permanent errors (bad input), call msg.ack() to avoid infinite retry.
        msg.retry({ delaySeconds: 30 });
      } else {
        await env.DB.prepare(
          `UPDATE inference_results
           SET status = 'done', output_text = ?, finished_at = ?
           WHERE id = ?`,
        ).bind(outcome.output, now, outcome.taskId).run();

        msg.ack();
      }
    }
  },
};
```

## Polling for Results

```typescript
// src/status.ts — HTTP endpoint to check task status
export default {
  async fetch(request: Request, env: Env & { DB: D1Database }): Promise<Response> {
    const url = new URL(request.url);
    const ids = url.searchParams.get("ids")?.split(",").filter(Boolean);

    if (!ids?.length) {
      return new Response("ids query param required", { status: 400 });
    }

    const placeholders = ids.map(() => "?").join(",");
    const { results } = await env.DB.prepare(
      `SELECT id, status, output_text, error, created_at, finished_at
       FROM inference_results
       WHERE id IN (${placeholders})`,
    ).bind(...ids).all();

    const summary = {
      total:   ids.length,
      done:    results.filter((r) => r.status === "done").length,
      pending: results.filter((r) => r.status === "pending").length,
      failed:  results.filter((r) => r.status === "failed").length,
      items:   results,
    };

    return Response.json(summary);
  },
};
```

## Anti-patterns

- **Using fetch() responses to deliver batch results**: the HTTP response returns
  before inference finishes; results must be stored durably (D1, R2) and polled.
- **Setting `max_batch_size` too high**: each AI call can take 5–30 s; with 20
  concurrent tasks and 30 s each, the batch can approach the consumer time budget.
  Keep `max_batch_size` at 5–10 and benchmark latency before increasing.
- **Acking all messages unconditionally**: calling `batch.ackAll()` at the start means
  failures are silently dropped—they never land in the DLQ. Ack/retry per-message.
- **Not setting a DLQ**: without a DLQ, messages that exhaust `max_retries` vanish.
  Always configure a separate DLQ queue and monitor its depth.
- **Storing large model outputs in Queue message bodies**: Queues cap message bodies at
  128 KB. Write results to D1/R2 and store only the task ID in the message.

## Gotchas

- **At-least-once delivery**: the same message can be delivered twice (e.g., after a
  partial consumer crash). Make your D1 writes idempotent: use `INSERT OR REPLACE` or
  check the current status before writing.
- **`max_batch_timeout`**: if the queue has fewer messages than `max_batch_size` but
  no new messages arrive, the consumer is triggered after `max_batch_timeout` seconds.
  Set it low (5–10 s) for interactive pipelines, higher (60 s) for overnight batches
  to maximise batching efficiency.
- **Queue backlog and rate-limiting**: Workers AI enforces per-account rate limits.
  If the queue depth grows faster than inference throughput, messages accumulate. Monitor
  the queue backlog metric in the Cloudflare dashboard and consider reducing producer
  throughput or requesting a rate-limit increase.
- **D1 write contention**: D1 serialises writes per database; at high concurrency,
  `UPDATE` contention may slow result recording. Use batch `prepare().bind()` patterns
  and avoid per-row round-trips.

## Verification

```bash
# 1. Enqueue a test batch
TASK_IDS=$(curl -s -X POST https://batch-inference.example.workers.dev/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "texts": ["The quick brown fox jumps over the lazy dog.", "Cloudflare is a cloud provider."],
    "prompt": "Summarise this in one sentence:"
  }' | jq -r '.taskIds | join(",")')

echo "Enqueued: $TASK_IDS"

# 2. Poll for results (allow 30–60s for inference)
sleep 30
curl -s "https://batch-inference.example.workers.dev/status?ids=${TASK_IDS}" | jq .

# 3. Inspect DLQ depth
wrangler queues list | grep dlq
wrangler queues consumer list ai-inference-dlq

# 4. Query D1 directly for failed rows
wrangler d1 execute inference-results \
  --command "SELECT id, error FROM inference_results WHERE status = 'failed' LIMIT 10"
```

## Related

- `llm-batch-processing.md`
- `llm-async-patterns.md`
- `workers-ai-function-calling-agentic-patterns.md`
- `llm-retry-patterns.md`
- `llm-timeout-handling.md`
- `ai-cost-monitoring.md`

## Sources

- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- Queues `sendBatch` API: https://developers.cloudflare.com/queues/configuration/javascript-apis/#producer
- Queues consumer settings: https://developers.cloudflare.com/queues/configuration/configure-queues/
- Workers AI limits: https://developers.cloudflare.com/workers-ai/platform/limits/
- D1 `prepare().bind()` docs: https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
