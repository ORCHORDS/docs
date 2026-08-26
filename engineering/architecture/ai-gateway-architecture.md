# ai-gateway-architecture

**Issue:** An application calls two or three LLM providers directly from feature code: API keys are scattered across services, there is no unified view of token spend, a provider outage takes the feature down because nothing retries elsewhere, and nobody can enforce a policy like "no PII leaves the boundary" or "cap this team at $500/month." The 2025-26 industry answer is the AI gateway — a proxy layer between application and model providers (Cloudflare AI Gateway, LiteLLM proxy, Kong AI Gateway, and equivalents) that centralizes routing, fallback, caching, budgets, and guardrails. Not covered anywhere else in this knowledge base; this article records the architecture, the routing strategies, and the failure modes.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why the layer exists (the problem shape)

1. **Provider sprawl.** Feature code that talks directly to OpenAI, Anthropic, Gemini, Bedrock, and self-hosted models bakes provider SDKs and request formats into every call site; an OpenAI-compatible gateway endpoint restores a single stable interface (this is LiteLLM's core pitch — one proxy format for 100+ providers).
2. **Spend opacity.** Token-based billing is invisible to request-level APM; without a metering point, finance discovers runaway spend from a credit-card bill. Gateways log cost per request, per key, and per team.
3. **No failure isolation.** LLM providers have meaningfully different uptime profiles; an app without provider-level retry and fallback converts any provider hiccup into a user-visible error.
4. **No policy enforcement point.** Rate limits, PII redaction, prompt allow/deny lists, and model allowlists have to be reimplemented per call site unless a proxy enforces them centrally — the same reasoning that produced API gateways in the 2010s, now applied to prompts and tokens.

## Core components

1. **Unified endpoint.** The app points at one URL with the gateway's auth (virtual keys), and the gateway translates to each provider's wire format; Cloudflare runs this at the edge, LiteLLM as a self-hosted proxy, Kong as plugins on its existing gateway.
2. **Provider routing and fallback.** Dynamic routing rules retry a failed request against an alternate model or provider (Cloudflare calls this retry/fallback via dynamic routing; Kong's AI Proxy Advanced does load balancing, retry, and multi-provider fallback), which is the single highest-value feature because it turns provider outages into non-events.
3. **Caching.** Exact-match response caching serves identical prompts without re-billing the provider; semantic caching matches by meaning rather than bytes and multiplies hit rates at the cost of occasionally returning a near-enough answer — a product decision, not a default.
4. **Virtual keys and budgets.** Per-team or per-feature keys carry their own spend caps and rate limits, so a runaway agent loop exhausts its own budget instead of the company card.
5. **Guardrails.** Prompt/response inspection runs at the proxy: allow/deny lists, topic-based semantic filtering, PII redaction (Kong's AI PII Sanitizer claims 20 categories across 9 languages), and integration with external safety services.
6. **Observability.** Structured logs of every prompt/response pair, token counts, latency, and cost per request — the dataset you need for evaluating model swaps later.

## Routing strategies

1. **Cost-based routing.** Send easy traffic to cheap models and hard traffic to expensive ones, either by explicit rule or by a classifier step; this is where the majority of spend savings come from.
2. **Latency and usage-aware balancing.** Lowest-latency and usage-weighted algorithms spread load across providers and regions (Kong ships round-robin, consistent hashing, lowest-latency, and usage-based options).
3. **Consistent-hash pinning.** Route by conversation or user hash so a session keeps hitting the same provider — necessary when provider-side prompt caching makes re-sending the same prefix nearly free but only within one deployment.
4. **Semantic routing.** Match requests to models by embedding similarity of the task rather than by rule; powerful but adds its own inference cost and a new thing that can misroute.
5. **Traffic mirroring for evaluation.** Shadow production prompts to a candidate model silently (LiteLLM supports this) to compare outputs before switching routes — the safe way to do a model migration.

## Failure modes

1. **The gateway is a new single point of failure.** A proxy that every AI feature depends on must have its own HA story; run it multi-instance, health-check providers independently, and make sure "gateway down" fails open to direct provider calls only if you accept losing policy enforcement.
2. **Fallback silently changes answer shape.** Retrying a Claude request against GPT changes tone, tool-calling format, and refusal behavior; fallback groups must contain behaviorally compatible models or the product degrades in ways tests will not catch.
3. **Caching leaks data across tenants.** A response cached for user A and served to user B is a data breach; cache keys must include tenant/user scope, and prompts containing PII should be excluded from shared caches entirely.
4. **Prompt logs become a liability.** Gateway-level logging captures user content at scale; define retention, redaction, and access rules for the log store before the first compliance question, not after.
5. **Token metering is not request metering.** Conventional rate limits count requests, but provider limits are tokens-per-minute; budget enforcement that ignores token dimension lets a single 200k-context request blow through caps.
6. **Key sprawl in reverse.** Virtual keys are still credentials; without rotation and per-key least privilege (model allowlists), the gateway concentrates blast radius instead of containing it.

## Related articles in this knowledge base

1. **`rate-limiter-design.md` and `throttling-patterns.md`.** Foundation for the token-aware limiting an AI gateway needs.
2. **`circuit-breaker-design.md` and `fallback-pattern.md`.** The primitives underneath provider fallback groups.
3. **`distributed-caching.md`.** Cache scoping and invalidation concerns that semantic caching inherits.
4. **`secret-management-architecture.md`.** Virtual key lifecycle and rotation.
