# LLM KV-Cache Prompt Prefix Reuse

Autoregressive text generation recomputes attention key/value tensors for every token position on every decoding step unless they are cached. When two requests share an identical token prefix — a long system prompt, few-shot block, or retrieved context — the key/value (KV) cache for that prefix can be computed once and reused. Prefix reuse is one of the highest-leverage and least glamorous optimizations in LLM serving: it converts quadratic recompute into a one-time cost, and its failure is usually silent, showing up only as unexplained latency and cost variance.

## Scope

This article covers the operational discipline of KV-cache prefix reuse in LLM inference services: how prefix matching actually works at the token level, how to structure prompts so prefixes hit, how to measure hit rates honestly, and what controls prevent correctness and cost regressions. It applies to self-hosted inference engines and hosted APIs that expose prompt caching as a feature.

It does not cover model architecture choices (multi-query or grouped-query attention reduce cache size but are model properties), quantization of the cache itself, or training-time optimizations. Those interact with reuse but are separate decisions.

A critical boundary: prefix reuse is token-exact in most engines. Semantically identical prompts that differ by one character, one space, or one reordered block miss the cache entirely. Treating cache behavior as a best-effort accelerator rather than a contracted guarantee is the safest operating posture.

## Workflow or implementation guidance

1. **Measure the baseline before optimizing.** Capture per-request prompt token counts, decode lengths, and time-to-first-token over a representative traffic window. Compute the theoretical saving: the fraction of prompt tokens that would hit if every request reused the longest common prefix with a warm cache. Requests with short, unique prompts gain nothing; requests with a 4,000-token shared preamble gain a lot.
2. **Order prompts from most stable to most volatile.** Put truly static content first (system role, tool definitions, formatting rules), then slowly changing content (retrieved documents pinned per session), then per-request content (the user question) last. A per-request token early in the prompt truncates reuse for everything after it. If the user question must appear early for quality reasons, measure whether the quality gain justifies the lost hits — this is an empirical trade, not a stylistic one.
3. **Confirm the engine's block granularity.** Prefix matching happens at block boundaries (commonly 16 or 128 tokens, engine-dependent). A shared prefix of 4,100 tokens with 128-token blocks yields 32 cached blocks and a 52-token tail computed fresh. Padding shared prefixes to whole blocks recovers the remainder where traffic shape allows.
4. **Bound the cache.** Decide how many prefixes to keep and the eviction policy. An unbounded cache in front of diverse traffic thrashes: each new long prefix evicts candidates that later requests wanted. Size the cache to the working set of hot prefixes — typically system prompts times active tenants — not to total traffic diversity.
5. **Namespace per tenant and per model version.** Most engines match prefixes globally; a hit from another tenant's identical system prompt is functionally safe (the tokens are the same) but makes hit-rate accounting misleading, and a model-version change silently invalidates every block. Tag metrics with model version and tenant so both effects are visible.
6. **Re-measure after changes.** Any prompt template edit, tool-definition reorder, or system-prompt wording change is a cache-invalidating deployment. Treat prompt template changes with the same rollout discipline as code: staged rollout, hit-rate watch, rollback path.

## Controls

- **Hit-rate dashboard per model and tenant.** Prompt-cache hit tokens divided by total prompt tokens, watched for step changes. A sudden drop after a deploy is the primary detection signal for accidental template drift.
- **Prompt template versioning.** Templates live in version control; the deployed template hash is logged per request (or sampled) so hit-rate regressions can be joined to template changes.
- **Cache budget alerts.** Cache memory consumption bounded and alerted; eviction-rate metrics distinguish "healthy churn" from "thrashing."
- **Cost reconciliation.** For hosted APIs with cached-token pricing, reconcile billed cached tokens against measured hit rates monthly. A mismatch indicates the client is not sending the exact bytes it thinks it is.
- **Change review gate for prompt structure.** A checklist item on every prompt-template PR: does this change alter any shared prefix? If yes, expected hit-rate impact is stated in the PR.

## Validation evidence

Validation rests on before/after measurements over real traffic, not synthetic microbenchmarks:

- Time-to-first-token distribution at matched traffic before and after prefix restructuring, reported at p50/p95/p99. A real improvement shows at p95 and above, where long prompts live.
- Hit-rate counters from the engine (blocks hit / blocks needed) cross-checked against an independent estimate: the longest-common-prefix statistics computed from logged prompt token sequences.
- Billed-token reconciliation for hosted caches: cached-input tokens on the invoice divided by total input tokens should track the measured hit rate within sampling error.
- A deliberate canary: change one byte in the shared system prompt, confirm hit rate collapses to near zero, revert, confirm recovery. This proves the measurement path, not just the cache.

## Failure modes and correction

- **Silent template drift.** A "harmless" wording tweak in the system prompt drops the hit rate and nobody notices until the invoice lands. Correction: alert on hit-rate step changes and page the owning team; template hash logging makes the culprit identifiable in minutes.
- **Dynamic content at the head.** Timestamps, request IDs, or personalization injected before the shared block truncate reuse for the entire prompt. Correction: move volatile fields to the prompt tail; if the head must vary, evaluate whether it can vary per day rather than per request.
- **Cross-tenant accounting confusion.** Identical public system prompts across tenants inflate per-tenant hit rates. Correction: segment metrics by tenant when evaluating per-tenant economics; treat global hits as valid reuse but separate them in reporting.
- **Eviction thrash.** Cache sized below the hot-prefix working set produces high eviction and low hit rates despite correct prompt structure. Correction: compute working-set size empirically (distinct hot prefixes × blocks each) and raise the budget above it; watch eviction counters confirm the fix.
- **Model-version invalidation during rollout.** A new model version cold-starts every cache; latency spikes are misread as a model regression. Correction: pre-warm by replaying representative prompts at rollout, and exclude the warm-up window from SLO calculations.

## Limitations

Cache behavior is engine-specific: block sizes, matching scope, eviction, and whether hits are guaranteed or best-effort all vary and change between versions. This article describes the discipline of measuring and structuring for reuse, not any one engine's contract. Prefix reuse does not reduce decode-time cost — only prompt processing — so workloads with short prompts and long generations see little benefit. Hosted caches may have minimum prefix lengths, TTL-based expiry, and regional scoping; consult the provider's current documentation for the binding numbers, which change frequently.

## Canonical sources

- vLLM documentation, Automatic Prefix Caching: https://docs.vllm.ai/en/latest/automatic_prefix_caching.html
- OpenAI documentation, Prompt Caching: https://platform.openai.com/docs/guides/prompt-caching
