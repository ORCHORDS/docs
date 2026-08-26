# Workers AI Batch Inference Throughput

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project runs Workers AI for content moderation (text classification), post embedding generation
(semantic search), and image labelling. Calling `env.AI.run()` once per item in a loop
sequentialises GPU work, wastes neuron quota, and causes p99 latency to grow linearly with batch
size. On moderation queues that process 50–200 posts per second, sequential inference saturates
the Neuron (AI Gateway) unit budget before peak traffic ends.

## Context

Workers AI exposes a single `env.AI.run(model, inputs)` call that accepts either a single input
object or, for supported models, an array of inputs enabling true batch inference on the GPU.
Batching amortises model-load overhead and increases hardware utilisation. The AI Gateway also
enforces per-minute neuron limits, so reducing round-trips per token directly raises effective
throughput ceiling before rate-limit kicks in.

## Section 1 — Measure Sequential vs Batch Baseline

Establish a timing benchmark comparing the naive sequential approach with the batched call to
quantify the improvement before optimising.

```typescript
// src/benchmarks/ai-sequential-vs-batch.ts
import type { Ai } from "@cloudflare/workers-types";

const TEXTS = Array.from({ length: 20 }, (_, i) => `Sample post number ${i} for moderation`);

export async function benchmarkSequential(ai: Ai): Promise<number> {
  const start = Date.now();
  for (const text of TEXTS) {
    await ai.run("@cf/huggingface/distilbert-sst-2-int8", {
      text,
    });
  }
  return Date.now() - start; // typically 800–2000 ms for 20 items
}

export async function benchmarkBatch(ai: Ai): Promise<number> {
  const start = Date.now();
  await ai.run("@cf/huggingface/distilbert-sst-2-int8", {
    text: TEXTS, // array input — single GPU pass
  });
  return Date.now() - start; // typically 150–400 ms for same 20 items
}
```

Log the ratio: batch throughput is typically 4–8× higher for classification models because
tokenisation and attention computation are parallelised across the batch dimension on-GPU.

## Section 2 — Implement Queue-driven Batch Accumulation

Enqueue moderation requests from the hot path (post-create handler) and drain them in a Queue
consumer that accumulates up to a maximum batch size before calling AI.

```typescript
// src/queues/moderation-consumer.ts
interface ModerationJob {
  postId: string;
  content: string;
}

interface ClassificationResult {
  label: "POSITIVE" | "NEGATIVE";
  score: number;
}

export async function handleModerationBatch(
  batch: MessageBatch<ModerationJob>,
  env: Env
): Promise<void> {
  const messages = batch.messages;

  if (messages.length === 0) return;

  // Build text array for batch inference
  const texts = messages.map((m) => m.body.content);

  // Single AI call for entire batch — GPU processes all texts in one forward pass
  const results = await env.AI.run(
    "@cf/huggingface/distilbert-sst-2-int8",
    { text: texts }
  ) as ClassificationResult[];

  // Write moderation outcomes back to D1
  const updateStmt = env.DB.prepare(
    "UPDATE posts SET moderation_label = ?, moderation_score = ? WHERE post_id = ?"
  );

  const batch_results = await env.DB.batch(
    messages.map((msg, i) =>
      updateStmt.bind(
        results[i]?.label ?? "POSITIVE",
        results[i]?.score ?? 1.0,
        msg.body.postId
      )
    )
  );

  // Ack all messages; retry individual failures via dead-letter queue
  const failedIds = new Set(
    batch_results
      .map((r, i) => (!r.success ? messages[i].id : null))
      .filter(Boolean)
  );

  for (const msg of messages) {
    if (failedIds.has(msg.id)) {
      msg.retry({ delaySeconds: 30 });
    } else {
      msg.ack();
    }
  }
}
```

## Section 3 — Parallel Multi-model Inference with Promise.all

For example project posts that require both classification (toxicity) and embedding (semantic index),
fan out to both models simultaneously rather than sequentially. Workers AI calls are I/O, so
`Promise.all` yields true parallelism within the Worker's subrequest budget.

```typescript
// src/lib/ai-enrichment.ts
interface PostEnrichment {
  toxicityLabel: string;
  toxicityScore: number;
  embedding: number[];
}

export async function enrichPost(
  ai: Ai,
  content: string
): Promise<PostEnrichment> {
  // Fire both models at once — no serialisation penalty
  const [classResult, embedResult] = await Promise.all([
    ai.run("@cf/huggingface/distilbert-sst-2-int8", { text: content }) as Promise<
      { label: string; score: number }[]
    >,
    ai.run("@cf/baai/bge-small-en-v1.5", {
      text: [content],
    }) as Promise<{ data: number[][] }>,
  ]);

  const top = classResult[0] ?? { label: "POSITIVE", score: 1.0 };

  return {
    toxicityLabel: top.label,
    toxicityScore: top.score,
    embedding: embedResult.data[0] ?? [],
  };
}

// Batch variant: enrich up to 20 posts simultaneously
export async function enrichPostBatch(
  ai: Ai,
  posts: { postId: string; content: string }[]
): Promise<(PostEnrichment & { postId: string })[]> {
  const contents = posts.map((p) => p.content);

  const [classResults, embedResults] = await Promise.all([
    ai.run("@cf/huggingface/distilbert-sst-2-int8", {
      text: contents,
    }) as Promise<{ label: string; score: number }[]>,
    ai.run("@cf/baai/bge-small-en-v1.5", {
      text: contents,
    }) as Promise<{ data: number[][] }>,
  ]);

  return posts.map((p, i) => ({
    postId: p.postId,
    toxicityLabel: classResults[i]?.label ?? "POSITIVE",
    toxicityScore: classResults[i]?.score ?? 1.0,
    embedding: embedResults.data[i] ?? [],
  }));
}
```

## Section 4 — AI Gateway Rate-limit Aware Backpressure

Workers AI enforces neuron-per-minute limits. Implement exponential backoff with jitter in the
Queue consumer to avoid 429s degrading the entire moderation pipeline.

```typescript
// src/lib/ai-with-retry.ts
export async function aiRunWithBackoff<T>(
  ai: Ai,
  model: string,
  inputs: unknown,
  maxAttempts = 3
): Promise<T> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return (await ai.run(model, inputs as Parameters<Ai["run"]>[1])) as T;
    } catch (err: unknown) {
      const isRateLimit =
        err instanceof Error &&
        (err.message.includes("429") || err.message.includes("rate limit"));

      if (!isRateLimit || attempt === maxAttempts - 1) throw err;

      // Exponential backoff: 200 ms, 400 ms, 800 ms + jitter
      const delay = Math.min(200 * 2 ** attempt + Math.random() * 100, 1000);
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw new Error("ai-run exhausted retries");
}
```

Configure wrangler.toml Queue consumer batch settings to control accumulation window:

```toml
[[queues.consumers]]
queue = "moderation-queue"
max_batch_size = 25       # Max items per consumer invocation
max_batch_timeout = 2     # Wait up to 2 s to fill a batch
max_retries = 3
dead_letter_queue = "moderation-dlq"
```

## Anti-patterns

- Calling `ai.run()` inside `Array.prototype.forEach` — forEach ignores returned Promises;
  use `Promise.all(items.map(...))` or a Queue consumer instead
- Batching more than the model's documented max sequence count — returns 400 errors
- Sending embeddings back to the client over the wire — store in Vectorize and return only the id
- Using Workers AI for real-time inference in the p50 critical path — latency is 50–300 ms;
  precompute or cache results; only use live inference in async Queue consumers
- Mixing models with different input shapes in a single `Promise.all` without proper typing

## Gotchas

- Not all Workers AI models support array/batch inputs; check the model card on
  https://developers.cloudflare.com/workers-ai/models/ — classification and embedding models do,
  but generative text models typically do not
- Queue `max_batch_size` is an upper bound, not a guarantee; the consumer may receive as few as
  1 message if the timeout fires first — always handle variable-length batches
- Embedding vectors returned by `bge-small-en-v1.5` are 384-dimensional float32 arrays;
  serialising to JSON for D1 storage is expensive — store in Vectorize instead
- Workers AI subrequests count against the Worker's 1000 subrequest limit per invocation

## Verification

```bash
# Monitor neuron usage via AI Gateway dashboard
# Workers > AI > Usage > Neurons Used (compare per-model per-hour)

# Tail Queue consumer logs to observe actual batch sizes
npx wrangler tail --format=json --env production \
  | jq 'select(.scriptName == "moderation-consumer") | .logs'

# Measure latency percentiles before/after batching
npx wrangler tail --format=json \
  | jq 'select(.outcome == "ok") | .wallTimeMs' \
  | sort -n | awk 'NR==int(0.99*NR){print "p99:", $0}'
```

## Related

- `/documentation/docs/policies/performance/workers-ai-inference-response-caching.md`
- `/documentation/docs/policies/performance/workers-ai-model-warmup-priming.md`
- `/documentation/docs/policies/performance/workers-ai-token-streaming-latency.md`
- `/documentation/docs/policies/performance/queues-throughput-batching.md`
- `/documentation/docs/policies/performance/vectorize-query-latency-optimization.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/platform/limits/
- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- https://developers.cloudflare.com/workers-ai/configuration/ai-gateway/
- https://developers.cloudflare.com/queues/reference/batch-settings/
