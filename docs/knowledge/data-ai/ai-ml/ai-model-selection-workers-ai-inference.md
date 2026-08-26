# ai-model-selection-workers-ai-inference

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

The example project Worker uses three different LLMs for content
suggestions, moderation, and post summarisation — chosen
by familiarity rather than benchmarking. P95 mobile latency
for the suggestion feature is 3-5 s due to an over-sized
model. Switching models for cost savings is blocked by fear
of accuracy regression with no baseline to compare against.

## Context

Workers AI serves inference at the Cloudflare edge with no
egress cost and no GPU provisioning. Model selection affects
latency, accuracy, and the Workers AI token budget (100k
tokens/min per account). example project has three inference tasks:
(1) real-time content suggestions (mobile SSE, latency-
sensitive), (2) batch moderation verdicts (cacheable), and
(3) post summarisation (async, quality-sensitive).

## 1. Workers AI Model Catalogue (2026-08 Snapshot)

```
Model                                  Params  CTX    TTFT*  Best for
-------------------------------------  ------  -----  -----  ----------------
@cf/meta/llama-3.3-70b-instruct-fp8   70B     128k   350ms  Quality tasks
@cf/meta/llama-3.1-8b-instruct        8B      128k   180ms  Fast path / mod
@cf/meta/llama-3.2-3b-instruct        3B      128k   80ms   Ultra-low lat
@cf/qwen/qwen2.5-coder-32b            32B     32k    250ms  Code tasks
@cf/mistral/mistral-7b-instruct-v0.2  7B      32k    200ms  Legacy, avoid
@cf/baai/bge-base-en-v1.5             —       —      80ms   Embeddings 768d
@cf/baai/bge-small-en-v1.5            —       —      40ms   Embeddings 384d
```

* TTFT = time-to-first-token on warm GPU at Cloudflare PoP.
  Values are approximate median; P95 is 2-3× higher.

## 2. Task-to-Model Mapping for example project

```
Task                  Requirement        Recommended model
--------------------  -----------------  ----------------------------------
Content suggestions   < 600 ms TTFT,     @cf/meta/llama-3.1-8b-instruct
  (mobile SSE)          creative output  (upgrade to 70B if quality low)
Content moderation    < 200 ms, cached   @cf/meta/llama-3.2-3b-instruct
  (batch verdicts)      deterministic    + AI Gateway exact-match cache
Post summarisation    Quality > latency  @cf/meta/llama-3.3-70b-fp8-fast
  (async queue)         3-5 s OK         (run off critical path via Queue)
Post search           Semantic recall    @cf/baai/bge-base-en-v1.5
  (Vectorize)           768-d cosine     (768d balances recall vs latency)
```

Assign the smallest model that meets the accuracy bar.
Evaluate on a example project-specific eval set before shipping.

## 3. Mobile Inference Latency by Model and Network

```
Model               WiFi P50  LTE P50  LTE P95  3G P95
------------------  --------  -------  -------  -------
llama-3.2-3b        120 ms    180 ms   600 ms   1.8 s
llama-3.1-8b        200 ms    280 ms   900 ms   3.1 s
llama-3.3-70b-fp8   400 ms    550 ms   2.1 s    6+ s
```

Network latency contributes only to TTFT (first token
transfer), not per-token throughput. On 3G the connection
round-trip adds 300-600 ms on top of GPU inference. For
the real-time suggestion path targeting P95 < 1 s on LTE,
llama-3.1-8b is the ceiling; 70B is out of budget.

## 4. Batching to Stay Under the Token Budget

Workers AI limits are per Cloudflare account, not per Worker.

```
Limit                  Value      Impact
---------------------  ---------  ----------------------------
Max tokens/min         100 k      Shared across all models
Max requests/min/model 50         Per model per account
Max batch texts (embed) 100       Per env.AI.run call
Max concurrent streams  No hard limit (GPU-bound in practice)
```

For moderation at high QPS, cache + batch:

```typescript
const MODERATION_BATCH_SIZE = 10;

async function batchModerate(
  texts: string[],
  env: Env,
): Promise<string[]> {
  const results: string[] = [];

  for (let i = 0; i < texts.length; i += MODERATION_BATCH_SIZE) {
    const slice = texts.slice(i, i + MODERATION_BATCH_SIZE);
    // Sequential to stay under 50 req/min/model;
    // parallelize only if remaining budget allows
    const verdicts = await Promise.all(
      slice.map(t => env.AI.run(
        "@cf/meta/llama-3.2-3b-instruct",
        {
          messages: buildModerationPrompt(t),
          max_tokens: 5,       // ALLOW or BLOCK only
        },
        { gateway: { id: "example project-ai-gw", cacheTtl: 86400 } },
      )),
    );
    results.push(...verdicts.map(v => parseVerdict(v.response)));
  }
  return results;
}
```

Prefer the Queue consumer over in-request batching for burst
absorption — see `ai-ml/workers-ai-text-classification.md`.

## 5. Model Size vs Accuracy Trade-offs

Run a one-time offline eval before choosing a model:

```typescript
// eval-runner.ts (run locally, not in production)
const EVAL_PAIRS: { input: string; expected: string }[] = [
  { input: "buy cheap meds now",  expected: "BLOCK" },
  { input: "anyone free tonight", expected: "ALLOW" },
  // ... 200+ samples from real example project data
];

async function runEval(model: string) {
  let correct = 0;
  for (const pair of EVAL_PAIRS) {
    const r = await ai.run(model, {
      messages: buildModerationPrompt(pair.input),
      max_tokens: 5,
    });
    if (parseVerdict(r.response) === pair.expected) correct++;
  }
  return correct / EVAL_PAIRS.length;
}

// Results (example example project eval set):
// llama-3.2-3b:  accuracy 88%, latency 120ms
// llama-3.1-8b:  accuracy 93%, latency 200ms
// llama-3.3-70b: accuracy 97%, latency 400ms
```

For moderation: 88% is often acceptable if humans review
the 12% edge cases. For content suggestions: quality loss
is directly user-visible — run A/B test, not just offline
eval.

## 6. Streaming Configuration per Model

Not all Workers AI models support the same streaming flags:

```
Model                  stream   max_tokens  Notes
---------------------  -------  ----------  --------------------
llama-3.3-70b-fp8      Yes      4096        Use for suggestions
llama-3.1-8b           Yes      4096        Use for fast path
llama-3.2-3b           Yes      512         Limited output len
bge-base-en-v1.5       No       N/A         Embedding only
```

For SSE streaming, always set `stream: true` and return the
`ReadableStream` directly:

```typescript
const stream = await env.AI.run(
  "@cf/meta/llama-3.1-8b-instruct",
  { messages, stream: true, max_tokens: 256 },
);
// Do NOT await the stream — return it immediately
return new Response(stream as ReadableStream, {
  headers: { "Content-Type": "text/event-stream" },
});
```

For non-streaming batch tasks, omit `stream: true` to get
the complete response in one await — saves the overhead of
SSE framing on short outputs.

## Anti-patterns

- Defaulting to the largest available model for all tasks —
  70B at 400 ms TTFT blocks the mobile suggestion UX; use
  8B unless the eval gap justifies the latency cost.
- Mixing models mid-conversation — switching from 8B to 70B
  mid-thread changes tone and instruction-following behaviour.
- Setting `max_tokens` too high on classification tasks — a
  `max_tokens: 2048` moderation call is 10× more expensive
  in tokens than `max_tokens: 5` for a BLOCK/ALLOW verdict.
- Sharing the Workers AI token budget between real-time and
  batch workloads — rate-limit the batch Queue consumer so
  mobile critical-path requests are never starved.
- Not pinning model IDs in `wrangler.toml` — Workers AI may
  alias `@cf/meta/llama-3-8b` to a newer version; always
  use the full versioned slug.

## Gotchas

- GPU cold-start adds 200-800 ms for less-popular models;
  Llama 3.x and Qwen 2.5 are warm globally, niche fine-tunes
  are not. Test cold latency before committing.
- `@cf/mistral/mistral-7b-instruct-v0.2` is kept for
  compatibility but no longer the recommended fast model;
  the llama-3.1-8b and llama-3.2-3b models are faster and
  more accurate on instruction-following tasks.
- Workers AI does not support custom fine-tunes as of 2026-08
  on the shared GPU tier; the model list is fixed.
- `max_tokens` limits output length but does not reduce input
  processing cost — long prompts consume the same tokens
  regardless of how short the output is.
- Running multiple AI tasks in `Promise.all` inside a single
  Worker request can exceed the 50 req/min/model limit when
  handling burst traffic; serialise or use Queues.

## Verification

```bash
# 1. Compare TTFT across models for the suggestion task
for MODEL in \
  "@cf/meta/llama-3.2-3b-instruct" \
  "@cf/meta/llama-3.1-8b-instruct" \
  "@cf/meta/llama-3.3-70b-instruct-fp8-fast"; do
  echo -n "$MODEL: "
  curl -o /dev/null -w "%{time_starttransfer}s\n" \
    -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCT/\
ai/run/${MODEL}" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"suggest a topic"}]}'
done

# 2. Confirm max_tokens constraint on moderation route
curl -si -X POST https://example project.example.com/api/moderate \
  -d '{"text":"hello world"}' \
  | jq '{verdict: .verdict, tokens_used: .usage.completion_tokens}'
# Expect: tokens_used < 10

# 3. Check Workers AI usage vs limits in dashboard
# AI > Workers AI > Usage — ensure batch jobs are not
# consuming > 80% of token budget
```

## Related

- `cloudflare/workers-ai-2026.md`
- `cloudflare/workers-ai-edge-inference.md`
- `cloudflare/workers-ai-mobile-inference-latency.md`
- `ai-ml/ai-model-selection-workers-ai-inference.md`
- `ai-ml/llm-context-window-cloudflare-workers.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/platform/limits/
- https://developers.cloudflare.com/workers-ai/configuration/
- https://blog.cloudflare.com/workers-ai/
- https://blog.cloudflare.com/how-cloudflare-runs-more-ai-models-on-fewer-gpus/
- https://blog.cloudflare.com/best-place-region-earth-inference/
