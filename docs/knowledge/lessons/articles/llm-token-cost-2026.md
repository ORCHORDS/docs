# llm-token-cost-2026

**Issue:** A 10,000-token prompt costs $0.30 per request on Anthropic, $0.45 on OpenAI. At 100,000 requests/day, that's $30k-$45k/day on input tokens alone. Caching, batching, and compression can drop this 40-85%; most teams don't apply them.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

LLM cost optimization is treated as a single lever. It's a stack of compounding levers, applied in the right order. A team that applies only one of them saves 30-50%; a team that applies five saves 70-90%. The cheapest moves (prompt caching, batching) are the ones most often skipped.

## Root cause

The cost model has six dimensions, and teams optimize for the wrong one:

1. **Per-token cost** (input vs. output, cached vs. uncached)
2. **Volume** (how many requests per day)
3. **Routing** (which model each request hits)
4. **Caching** (prompt cache hit rate, semantic cache hit rate)
5. **Batching** (sync vs. async endpoint usage)
6. **Compression** (input token count after compression)

Defaulting to "all requests hit the frontier model" wastes 60-90% of cost on the bulk of traffic.

## The 7-lever compounding stack

In order of effort (cheapest first):

| # | Lever | Typical savings | Effort | Risk |
|---|---|---|---|---|
| 1 | Provider prompt caching | 50-90% on cached input tokens | 1 day | None — pure reorder |
| 2 | Batch API for async work | 50% vs. live | 1-2 days | Latency only acceptable for non-real-time |
| 3 | Model routing (cheap default + escalation) | 30-60% on routed workloads | 1-2 weeks | Quality risk on borderline tasks |
| 4 | Output length control (max_tokens, structured output) | 10-30% on output | 1 day | Quality risk if too tight |
| 5 | Semantic caching for repeated queries | 15-40% on cache hit | 1-2 weeks | False-positive risk on threshold tuning |
| 6 | Prompt compression (LLMLingua, TAAC) | 44-89% on compressed prompts | 2-4 weeks | Quality risk on heavy compression |
| 7 | Self-hosting at volume | 5-30x per-query at scale | Months | Ops cost, GPU provisioning |

A team that applies levers 1-4 typically saves 60-80% within 2-3 weeks. Adding 5-7 takes it to 85-95%.

## The prompt caching discipline

Provider prompt caching is the single biggest lever for most workloads in 2026. The mechanism: when a request's prompt prefix matches a previous request's prefix, the provider serves the cached prefix at a fraction of normal pricing.

| Provider | Cached input discount | Minimum prefix | Cache TTL |
|---|---|---|---|
| Anthropic | ~90% off | 1024 tokens | 5 min default; 1h at 2x write cost |
| OpenAI | ~50% off | 1024 tokens | 5-10 min, automatic |
| Google Gemini | ~90% off (cache hit costs ~10% of base) | 1024-2048 tokens | Up to 1 hour |

The engineering rule: **stable at the front, dynamic at the rear**.

- System prompts, tool definitions, RAG context, few-shot examples — all at the beginning
- User message, session variables, dynamic tool outputs — at the end
- Cache isolation is per-workspace since February 2026; not org-wide

```python
# Anthropic example
response = client.messages.create(
    model="claude-sonnet-4-6",
    system=[
        {
            "type": "text",
            "text": LONG_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}  # <-- explicit cache breakpoint
        }
    ],
    messages=[{"role": "user", "content": user_input}]  # dynamic, not cached
)
```

Without `cache_control`, Anthropic will still auto-cache prefixes above 1024 tokens, but explicit breakpoints give precise control.

Target cache hit rate: 70%+ for any agent with a stable system prompt + tool schema. Below that, the cache isn't pulling its weight.

## The batch API discipline

Every major provider offers a batch endpoint at roughly half the live rate, in exchange for an asynchronous completion window (typically 24h, sometimes 1h for OpenAI).

What runs on batch:

- Evaluations
- Bulk classification
- Enrichment
- Summarization
- Embedding generation

What doesn't:

- Real-time chat
- Interactive tool use
- Anything with sub-second latency requirement

The mistake: running batch-eligible work on the live endpoint. A 10k-request classification job at $0.50/1M output on live becomes $0.25/1M on batch — same quality, half the cost.

## The semantic caching discipline

Semantic caching operates at a different layer than provider prompt caching:

- **Provider prompt cache:** still invokes the model; just reduces input token cost for cache hits
- **Semantic cache:** avoids the model call entirely; zero tokens consumed; sub-100ms response

Implementation: embed the incoming query (text-embedding-3-small or sentence-BERT), compare against cached embeddings in a vector store (Redis, Pinecone, Qdrant), return cached response if similarity exceeds threshold.

| Threshold | Behavior |
|---|---|
| 0.85 | Aggressive — more hits, more false positives |
| 0.90-0.95 | Balanced — typical for general Q&A |
| 0.95-0.97 | Conservative — for code, exact-match-style queries |

Hit rate on a high-repetition workload (FAQ, code search, tool result caching) is 15-40%; cost reduction matches the hit rate.

The gotcha: semantic cache must have a TTL. "What is the current CEO of company X" cached for 30 days serves stale answers. Set TTL based on content freshness requirement.

## The compression discipline

When prompt caching and semantic caching don't apply (genuinely novel query, no semantic neighbor), the next lever is prompt compression.

**LLMLingua** compresses prompts 50-80% with minimal performance loss. Particularly effective for RAG with long retrieved contexts.

**Task-Aware Adaptive Compression (TAAC)** reduces inference cost up to 93% by adapting compression rate to task complexity.

```python
from llmlingua import PromptCompressor

compressor = PromptCompressor()
compressed = compressor.compress_prompt(
    long_rag_context,
    question=query,
    target_token=500,  # compress to 500 tokens
)
```

The risk: aggressive compression can degrade quality on tasks that depend on fine-grained context. Always run the eval set after compression to verify the quality bar.

## The Cache-Aware Prompt Compression (CAPC) pattern

A 2026 paper (`arxiv 2607.15516`) shows that combining prompt caching with prompt compression needs care. The naive combination (compress, then cache) can push the cached prefix into the hot tier, where the cost model changes.

The CAPC pattern:

- **Query-agnostic compression** for the static prefix (system prompt, tool schemas)
- **Query-aware compression** for the dynamic per-request context (RAG, user message)
- **Cache_control with tier-preserving ratio bound** to prevent over-compression

CAPC achieves 49% mean savings over cache-only, 64% over query-aware compression, and 90% over vanilla, at quality within 0.05 of the uncompressed baseline. Validated on three production workloads: enterprise tool-using assistant (51.7% cost reduction at r=3), RAG pipeline (9.3x on FastAPI codebase, 2.4x on httpx), and tau-bench retail (cheapest of four strategies, equal quality to vanilla).

The point: combining caching and compression is not a free win. The compression ratio has to respect the cache tier. CAPC is the first production-validated way to do it.

## The cost calculation discipline

For every LLM call, capture:

- prompt_tokens (input, including cached portion)
- completion_tokens (output)
- cached_tokens (input that hit the cache)
- model
- latency_ms
- cost_usd
- feature, team, environment tags

The cost formula:

```python
cost = (prompt_tokens * input_cost + completion_tokens * output_cost) / 1_000_000
# cached portion of prompt_tokens is at cached_input_cost
```

Track p50 and p95 of cost per request by feature, by team, by model. Alert on cost drift (>20% week-over-week). Without per-request cost, optimization is guesswork.

## Verification

The tell that the cost optimization stack is working:

- A single dashboard shows cost per request, broken down by feature and model
- Cache hit rate is >70% on the system prompt prefix
- Batch is the default for all async work; live is the exception
- Routing escalation rate is tracked and tuned per task
- Cost per active user is a tracked metric, not a finance team's quarterly surprise

The tell it isn't:

- One model handles everything; cost is whatever the frontier charges
- Caching is "in theory" but no cache hit rate is measured
- Batch-eligible work runs on the live endpoint

## Gotchas

- **Provider caching has minimum prefix length.** 1024 tokens for Anthropic and OpenAI. Below that, no cache, full price.
- **Cache isolation is per-workspace, not org-wide.** A cache hit in workspace A doesn't warm the cache for workspace B.
- **Semantic cache threshold is a knob.** 0.92-0.97 is the band. Too low and you serve wrong answers; too high and you never hit.
- **Batch has 24h latency.** Don't put real-time work in batch; you'll miss SLAs.
- **Compression can degrade quality.** Always run the eval set after enabling compression.
- **Self-hosting has hidden costs.** GPU hours, electricity, MLOps. Self-host at volume or compliance, not for ideological reasons.

## Related

- `patterns/prompt-caching-2026.md` — the cache_control wiring
- `patterns/agent-routing-2026.md` — the routing implementation
- `lessons/ai-cost-finops-2026.md` — the FinOps stack
- `lessons/ai-model-selection-2026.md` — choosing the right model per task

## Source URLs (verified 2026-08-10)

- https://redis.io/blog/llm-token-optimization-speed-up-apps/
- https://baeseokjae.github.io/posts/llm-cost-reduction-strategies-2026/
- https://wavect.io/blog/reduce-llm-token-costs-2026/
- https://www.obviousworks.ch/en/token-optimization-saves-up-to-80-percent-llm-costs/
- https://callsphere.ai/blog/llm-caching-strategies-cost-optimization-2026
- https://aisuperior.com/llm-cost-optimization-strategies-2026/
- https://arxiv.org/abs/2607.15516
- https://developer.konghq.com/cookbooks/llm-cost-optimization/
