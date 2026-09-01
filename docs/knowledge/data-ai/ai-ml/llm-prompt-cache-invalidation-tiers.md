# LLM Prompt Cache Invalidation Tiers

Prompt caching fails in a particular way: not with an exception, but with a hit rate that quietly walks toward zero. The cause is almost always invalidation design — some component of the "shared" prefix turns out to change, and every change truncates reuse for everything after it. Treating the prompt as a set of tiers with distinct volatility, and assigning each tier an explicit invalidation policy, turns cache behavior from an emergent accident into a designed property with predictable economics.

## Scope

This article covers the tiered design of prompt prefixes for cache reuse: classifying prompt components by volatility, ordering tiers for maximum reuse, invalidation triggers per tier, and the measurement that verifies the design holds in production. It applies to services using engine-level prefix caching or provider prompt-caching features.

Excluded: KV-cache internals and block mechanics (covered by the prefix-reuse article in this family) and general response caching of completed generations, which has different keys and policies.

The organizing principle is a simple inequality: reuse extends only up to the first differing token. Therefore prompt structure should be a volatility gradient — most-stable content first, most-volatile last — and every tier boundary is a place where an invalidation policy must be declared, because an undeclared one is still enforced, by cache miss, at runtime.

## Workflow or implementation guidance

1. **Inventory prompt components and classify volatility.** List every segment that composes prompts: system instructions, tool schemas, persona text, retrieval corpora, conversation history, user input, per-request metadata. For each, state its change frequency and change trigger — "changes with each release," "changes daily with the document set," "changes per session," "changes per request." This inventory is the design document; every component without a volatility class is a latent miss.
2. **Order tiers strictly by volatility.** Tier 0: static system prompt and tool definitions, changing only at deploy. Tier 1: slow-moving shared context — pinned documents, domain configuration — changing on a schedule. Tier 2: per-session state — conversation history, user preferences. Tier 3: per-request content — the current question. The ordering rule has no exceptions worth violating casually; one timestamp in tier 0 costs the whole cache.
3. **Declare the invalidation trigger per tier.** Tier 0 invalidates on template-version change (deploy event). Tier 1 invalidates on corpus-version change (data pipeline event, not a TTL guess). Tier 2 invalidates on session lifecycle events. Tier 3 never invalidates — it is born unique and dies with the request. Writing these down converts "why did hit rate drop" from archaeology into dashboard reading.
4. **Version the volatile-within-tier content explicitly.** Where tier 1 content updates (new document set), advance a version identifier in the prompt prefix itself where the engine requires alignment, so old and new versions do not contend for the same cache slots — different prefixes naturally separate, and eviction pressure stays predictable.
5. **Size the cache to tier working sets.** The memory needed is the sum over hot tenants of their tier-0/tier-1 footprints, plus headroom. Cache sizing from total traffic diversity over-provisions badly; sizing from the inventory above is arithmetic.
6. **Instrument tier boundaries.** Log, per request, the prefix length at each tier boundary and the engine-reported hit length. The difference localizes misses instantly: a hit length stuck at the tier-0 boundary means tier-1 content is changing per request — a design violation, not a tuning problem.

## Controls

- **Tier-structure lint.** A build-time check on prompt templates: declared tier order, no unreferenced dynamic injections into tiers 0–1. Template edits that smuggle volatile content forward fail CI.
- **Per-tier hit-length telemetry.** Distributions of engine hit lengths against tier boundaries; alarms when hits regress below a tier boundary for a traffic class.
- **Invalidation event log.** Deploy events, corpus-version bumps, and session-policy changes recorded, so hit-rate changes join to causes automatically.
- **Cache-budget review.** Working-set computation from the inventory reviewed when tenant count or tier-1 corpus size grows materially; the budget change is a planned event, not a discovered eviction crisis.
- **Template-version stamping.** Templates embed their version implicitly via content (the version changes the text), and the version is logged per request for attribution.

## Validation evidence

- Tier-hit matrix: for a sampled production window, fraction of requests achieving hits at least through each tier boundary, per tenant class — the design's report card.
- Before/after comparisons for structure changes (e.g., moving a per-request field from front to back), with hit-length distributions proving the predicted boundary shift occurred.
- Invalidation attribution: hit-rate dips correlated with the event log, demonstrating each dip maps to a declared trigger rather than an unknown cause.
- Working-set arithmetic: measured hot-prefix memory against configured budget, over time, showing the budget was derived and maintained rather than guessed.

## Failure modes and correction

- **Trojan timestamp.** A "generated at" field or request ID lands in the system prompt; hit rate collapses to near zero despite correct tiering elsewhere. Correction: the tier-structure lint catches template-level injections; runtime telemetry shows hits truncating at the tier-0 boundary, localizing the defect immediately.
- **Tenant-shared template divergence.** Each tenant's system prompt differs slightly (branding, policy), so tier 0 is not shared globally — by design, but then cache sizing must count per-tenant footprints, not one global prefix. Correction: working-set arithmetic per tenant class; alarms on eviction rate as tenants multiply.
- **Tier-1 churn from pipeline noise.** The corpus version bumps on trivial changes (whitespace normalization upstream), invalidating tier 1 repeatedly. Correction: corpus versions advance on semantic-change detection (content hashes over normalized text), not file timestamps.
- **History growth truncating nothing but budget.** Tier-2 conversation history grows per session until prompts exceed context limits, and cache economics degrade as sessions age. Correction: declared history-compaction policy with its own triggers; session-length telemetry against the compaction threshold.
- **Undeclared dependency discovered late.** A "static" tool schema actually embeds a dynamic capability list that varies by user entitlement — a hidden tier-3 component inside tier 0. Correction: entitlement-conditioned schemas move to their own tier ordered after tier 1; the tier inventory is updated so the class is explicit.

## Limitations

Engine caching mechanics — block granularity, global versus tenant-scoped matching, eviction policies, TTL behaviors — differ by engine and provider and change between versions; tier design must be validated against the current engine's documented semantics. Provider prompt caches may enforce minimum prefix sizes or per-region scoping that reshape tier economics. Tiering optimizes reuse, not quality; prompt ordering that maximizes cache hits can differ from ordering that maximizes answer quality for some models, and where they conflict the trade must be measured, not assumed. This article presumes read-mostly prompts; write-heavy conversation flows shift value toward tier-2-aware designs beyond its scope.

## Canonical sources

- Anthropic documentation, Prompt Caching: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- vLLM documentation, Automatic Prefix Caching: https://docs.vllm.ai/en/latest/automatic_prefix_caching.html
