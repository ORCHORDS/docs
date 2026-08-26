# agent-cost-optimization

**Issue:** Reducing LLM API spend by 50-80% — the 2026 playbook
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://platform.openai.com/docs/guides/batch)

## The 5 levers (in order of leverage)

Per the 2026 production literature, the typical LLM bill is
5-10x bloat. The fix is stacking 5-6 levers:

| # | Lever | Typical savings | Effort |
|---|---|---|---|
| 1 | **Prompt caching** (cache the stable prefix) | 50-90% on cached tokens | Low (hours) |
| 2 | **Model routing** (cheap model for easy tasks) | 40-60% | Medium (weeks) |
| 3 | **Batch API** for non-realtime | 50% on async workloads | Low (hours) |
| 4 | **Output-shape engineering** (JSON, max_tokens) | 20-40% | Low (hours) |
| 5 | **Semantic caching** (deduplicate identical queries) | 30-60% on repeated | Medium (days) |
| 6 | **Context management** (compression, sliding window) | 20-50% on long sessions | Medium (weeks) |

**Stacking all 6 = 70-85% bill reduction** (per multiple 2026
surveys). The user's router already does lever #2 (routing
easy/medium to local ollama). The `monitor/minimax-spend.json`
budget tracking is lever #0 (governance).

**Source:**
- Wring 2026: https://www.wring.co/blog/llm-inference-cost-optimization
- PremAI 2026: https://www.premai.io/blog/llm-cost-optimization-8-strategies-that-cut-api-spend-by-80-2026-guide/
- AI Superior: https://aisuperior.com/llm-cost-optimization-strategies-2026/
- GMI Cloud: https://www.gmicloud.ai/en/blog/llm-inference-cost-optimization-caching-batching-routing
- JobsByCulture: https://jobsbyculture.com/blog/llm-cost-optimization-guide-2026
- Baeseokjae: https://baeseokjae.github.io/posts/llm-cost-reduction-strategies-2026/

## Lever 1: Prompt caching

Anthropic prompt caching reduces input cost on the cached
prefix to 10% of base (90% discount). The cache requires:
- Stable prefix (system prompt, tool definitions)
- 1024+ tokens for Sonnet, 4096 for Opus
- Explicit `cache_control: { type: "ephemeral" }` markers
- Up to 4 breakpoints per request

**Caveat (March 6, 2026):** Anthropic changed default TTL
from 1 hour to 5 minutes. To use 1-hour cache, set
`ttl: 3600` explicitly. See `patterns/agent-context-engineering-2026.md`
for full details.

## Lever 2: Model routing

The user's `packages/router/src/route.js` implements this:
- easy/medium → ollama (local, free)
- hard → claude (SDK | API | deferred)

2026 routing patterns:
- **Difficulty classifier** (rules + optional LLM judge)
- **Cost router**: cost-weighted model selection
- **Quality router**: route to smallest model that meets quality bar on the eval set
- **Fallback chain**: if primary fails, next backend; all fail → deferred

The user's router has a 2-layer fallback chain (minimax →
claude-sdk → claude → deferred). Production 2026 chains are
typically 3-4 backends.

## Lever 3: Batch API

OpenAI Batch API, Bedrock Batch, Anthropic Batch — all
offer ~50% discount for async workloads with 24-hour SLA.
The user's router could expose a `batch=true` mode for
non-realtime tasks (RAG ingestion, eval runs, etc.).

**Production pattern:** collect requests into a queue,
flush to the batch API nightly, post results when the
batch completes.

## Lever 4: Output-shape engineering

- **Set `max_tokens` explicitly** for every API call
- **Request JSON** (40-60% shorter than prose)
- **Use stop sequences** to terminate generation when the useful part is done
- **Specify output format in the prompt** ("Respond in 2-3 sentences")
- **Structured outputs** (JSON schema) for tools

The user's MCP server already requires `{ content: [{ type: "text", text: "..." }] }`
per the MCP spec. The router + fleet could enforce this at
the boundary.

## Lever 5: Semantic caching

Deduplicate identical or near-identical queries before
they hit the model. 2026 best practice:
- Embed the query
- Cosine-similarity against a cache of recent queries
- If similarity > 0.95, return the cached response
- 30-60% savings on repeated-query workloads (FAQ, RAG)

Caveat: be careful with freshness. Stale cached answers
can be wrong answers.

## Lever 6: Context management

For long sessions, the context window grows monotonically.
Three patterns:
- **Sliding window** — keep last N turns
- **Compaction** — summarize older turns (75% threshold; see `agent-context-engineering-2026.md`)
- **RAG replacement** — retrieve relevant context instead of carrying all

The user's `packages/shared-memory/` does RAG replacement
over the KB. Compaction is in the roadmap.

## The 7-step implementation sequence

1. **Instrument** — per-request cost telemetry: input tokens, cached tokens, output tokens, model, route. Tag by feature.
2. **Cache and trim** — enable prompt caching on every route with stable prefix > 1K tokens; audit output bloat
3. **Move to batch** — any non-realtime workload → batch API
4. **Routing eval** — build a 200-500 example eval set; test smaller models; add difficulty router
5. **Semantic cache** — high-repeat query patterns
6. **Stabilize** — regression alerts (cost-per-request, quality-on-eval, cache hit rate)
7. **Document** — one place for routing logic per route

## The 6 anti-patterns

1. **Frontier model for every request** — 30-50% waste. 70% of requests don't need it.
2. **No prompt-cache hits** — 20-40% waste. Long system prompts re-billed in full each call.
3. **Bloated system prompts & few-shots** — 10-25% waste. Audit and compress.
4. **Unbounded retries on failure** — 5-15% waste. Set `attempts: 2` and surface to user.
5. **Real-time API for async workloads** — 10-30% waste. Batch would be 50% cheaper.
6. **No output-token discipline** — 10-20% waste. "Respond with explanation" instead of structured output.

## Related
- `patterns/agent-context-engineering-2026.md` — prompt caching in depth
- `cloudflare/workers-ai-2026.md` — the cheap-tier backend in the routing chain
- `packages/router/src/route.js` — the implementation
- `packages/router/src/fallback.js` — the fallback chain
- `packages/router/src/backends/minimax.js` — the budget tracking
- `packages/router/README.md` — the original routing design (DESIGN-ROUTER.md)
- `patterns/mcp-server-patterns.md` — MCP servers as a cost surface
