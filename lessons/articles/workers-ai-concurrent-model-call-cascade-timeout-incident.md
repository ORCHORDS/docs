# Workers AI Concurrent Model Call Cascade Timeout Incident

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

On 2026-07-28, example project's AI document-processing pipeline experienced a 34-minute total outage. Error rate reached 100% for the `POST /api/documents/analyse` endpoint. Root cause: a single slow Workers AI model invocation (`@cf/meta/llama-3-8b-instruct`) blocked the entire `Promise.all()` fan-out inside the Worker, holding the CPU time budget hostage until the 30-second wall-clock limit was exceeded. The Worker was then terminated mid-response, leaving Durable Object locks acquired but never released.

## Context

The document analysis Worker fans out to three AI models in parallel: a classifier, a summariser, and a key-phrase extractor. Engineers used `Promise.all()` without per-call timeouts, trusting Workers AI to respect its own internal deadlines. Under load, llama-3-8b-instruct experienced a cold start spike (>25 seconds), causing the entire `Promise.all()` to hang until the Worker's wall-clock limit killed it. All three results were discarded, and retry attempts compounded the load, triggering a cascade.

---

## Section 1: The Broken Fan-Out Pattern

```typescript
// BEFORE — unguarded Promise.all() with no per-call timeout
async function analyseDocument(
  text: string,
  env: Env
): Promise<DocumentAnalysis> {
  const [classification, summary, keyPhrases] = await Promise.all([
    env.AI.run('@cf/huggingface/distilbert-sst-2-int8', { text }),
    env.AI.run('@cf/meta/llama-3-8b-instruct', {
      messages: [{ role: 'user', content: `Summarise: ${text}` }],
    }),
    env.AI.run('@cf/baai/bge-small-en-v1.5', { text }),
  ]);

  return { classification, summary, keyPhrases };
}
```

A 25-second stall in the summariser blocked classification and key-phrase results even though they completed in 1-2 seconds.

---

## Section 2: Per-Call Timeout with AbortController

Wrap every Workers AI call in a race against an `AbortController`-backed timeout. Workers AI respects the `signal` option.

```typescript
// ai-utils.ts
export async function runWithTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  label: string
): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`AI call timeout: ${label} (${timeoutMs}ms)`)), timeoutMs);
  });

  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(timer!);
  }
}
```

---

## Section 3: Independent Fan-Out With Per-Model Timeouts

```typescript
// AFTER — independent calls with individual timeouts and graceful degradation
async function analyseDocument(
  text: string,
  env: Env
): Promise<DocumentAnalysis> {
  const CLASSIFIER_TIMEOUT_MS = 5_000;
  const SUMMARISER_TIMEOUT_MS = 15_000;
  const EMBEDDER_TIMEOUT_MS   = 8_000;

  const [classResult, summaryResult, phraseResult] = await Promise.allSettled([
    runWithTimeout(
      env.AI.run('@cf/huggingface/distilbert-sst-2-int8', { text }),
      CLASSIFIER_TIMEOUT_MS,
      'classifier'
    ),
    runWithTimeout(
      env.AI.run('@cf/meta/llama-3-8b-instruct', {
        messages: [{ role: 'user', content: `Summarise in 3 sentences: ${text}` }],
      }),
      SUMMARISER_TIMEOUT_MS,
      'summariser'
    ),
    runWithTimeout(
      env.AI.run('@cf/baai/bge-small-en-v1.5', { text }),
      EMBEDDER_TIMEOUT_MS,
      'embedder'
    ),
  ]);

  return {
    classification: classResult.status === 'fulfilled' ? classResult.value : null,
    summary:        summaryResult.status === 'fulfilled' ? summaryResult.value : null,
    keyPhrases:     phraseResult.status === 'fulfilled' ? phraseResult.value : null,
    degraded:       [classResult, summaryResult, phraseResult].some(r => r.status === 'rejected'),
  };
}
```

Using `Promise.allSettled` instead of `Promise.all` means a single model timeout does not cancel the others.

---

## Section 4: Queue-Based Retry for Degraded Results

When `degraded: true`, offload a retry job to a Queue rather than blocking the HTTP response.

```typescript
// document-worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { documentId, text }: AnalyseRequest = await request.json();

    const analysis = await analyseDocument(text, env);

    if (analysis.degraded) {
      await env.AI_RETRY_QUEUE.send({
        documentId,
        text,
        missing: {
          classification: analysis.classification === null,
          summary:        analysis.summary === null,
          keyPhrases:     analysis.keyPhrases === null,
        },
        retriedAt: Date.now(),
      });
    }

    await env.DB.prepare(
      'INSERT OR REPLACE INTO document_analysis VALUES (?, ?, ?, ?, ?)'
    ).bind(
      documentId,
      JSON.stringify(analysis.classification),
      analysis.summary,
      JSON.stringify(analysis.keyPhrases),
      analysis.degraded ? 'PARTIAL' : 'COMPLETE'
    ).run();

    return Response.json({ documentId, status: analysis.degraded ? 'partial' : 'complete' });
  },
};
```

---

## Section 5: Observability — Emit Per-Model Latency and Timeout Metrics

```typescript
// ai-instrumented.ts
export async function runWithMetrics<T>(
  modelId: string,
  promise: Promise<T>,
  timeoutMs: number,
  env: Env
): Promise<T | null> {
  const start = Date.now();
  try {
    const result = await runWithTimeout(promise, timeoutMs, modelId);
    env.ANALYTICS.writeDataPoint({
      blobs:   [modelId, 'success'],
      doubles: [Date.now() - start],
      indexes: [modelId],
    });
    return result;
  } catch (err) {
    const isTimeout = err instanceof Error && err.message.includes('timeout');
    env.ANALYTICS.writeDataPoint({
      blobs:   [modelId, isTimeout ? 'timeout' : 'error'],
      doubles: [Date.now() - start],
      indexes: [modelId],
    });
    console.error(`[AI] ${modelId} failed`, { error: String(err), durationMs: Date.now() - start });
    return null;
  }
}
```

Dashboard query: `SELECT blob1 AS model, blob2 AS outcome, avg(double1) AS avg_ms FROM ai_calls GROUP BY model, outcome ORDER BY avg_ms DESC` — surfaces which models are chronically slow before they cascade.

---

## Anti-patterns

- Using `Promise.all()` for Workers AI fan-outs without per-call timeouts — one slow model kills all results.
- Relying on the Worker's 30-second wall-clock limit as the only timeout signal — by then CPU time is exhausted and locks may not release cleanly.
- Retrying failed AI calls synchronously within the same Worker request — retry load compounds the cold-start cascade.
- Logging AI errors without the model ID — makes it impossible to identify which model caused production degradation.

## Gotchas

- Workers AI `run()` does not surface a built-in `timeout` option — timeouts must be implemented by the caller using `Promise.race`.
- Cold starts for large models (llama-3-8b+) can exceed 20 seconds; set `SUMMARISER_TIMEOUT_MS` conservatively to leave headroom before the 30s wall-clock.
- `Promise.allSettled` does not throw — always check `.status` before accessing `.value`; accessing `.value` on a rejected result returns `undefined` silently in some runtimes.
- Analytics Engine `writeDataPoint` is fire-and-forget; do not `await` it on the hot path.

## Verification

1. Load test with `k6` at 50 RPS against staging; inject artificial latency (>20s) to the summariser binding via a mock and confirm the endpoint returns `partial` within 16 seconds.
2. Confirm the retry queue receives messages for degraded documents within 5 seconds of the HTTP 200 response.
3. After retry worker processes the queue, verify `document_analysis.status` flips from `PARTIAL` to `COMPLETE` in D1.
4. Alert: Workers AI timeout rate > 2% over 5-minute window → PagerDuty P2.

## Related

- `workers-ai-cold-start-latency-production-lesson.md`
- `workers-ai-rate-limit-exceeded-production-incident.md`
- `workers-ai-model-capability-regression-postmortem.md`
- `queue-backlog-death-spirals.md`
- `circuit-breaker-prevents-cascade-failure.md`
- `timeouts-everywhere-no-exceptions.md`

## Sources

- Cloudflare Workers AI documentation — Limits: https://developers.cloudflare.com/workers-ai/platform/limits/
- Cloudflare Workers — CPU time and wall-clock limits: https://developers.cloudflare.com/workers/platform/limits/#worker-limits
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- example project incident ticket INC-2026-0728-AI-CASCADE
