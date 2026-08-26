# agent-routing-2026

- **Issue**: Sending every request to the frontier model is 5–10× more expensive than necessary, and using a tiny model for hard tasks tanks quality. The 2026 production pattern is a **layered cascade** that costs single-digit percent latency overhead and saves 40–85% on inference while keeping 90–95% of frontier quality.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/docs/policies/patterns/agent-cost-optimization.md` and `documentation/docs/policies/patterns/multi-agent-orchestration.md`.

## Symptom

- All requests go to the same frontier model. The bill is 8× what it should be.
- A small model handles easy tasks fine but you route hard tasks to it and quality drops.
- Your cascade adds 600–900 ms to the tail latency and tanks the user experience.
- You trained a routing classifier but it misroutes 25% of requests. The cost of bad routing exceeds the cost of just using the frontier.

## Root cause (the 2026 routing stack)

### The seven techniques

| Technique | Goal | Cost reduction vs frontier | Added latency | Implementation complexity |
|---|---|---|---|---|
| **Single Router (RouteLLM)** | Cost at fixed quality | 48–75% | +5–15 ms | Low |
| **Cascade (cheap → strong)** | Cost with quality floor | 70–80% | +0–400 ms (when escalating) | Medium |
| **Speculative-Race** | Latency with cost ceiling | -5 to +20% (slightly more expensive) | -30 to -60% (faster) | Medium |
| **Mixture-of-Routers (MoR)** | Multi-objective Pareto | 75–85% | +10–25 ms | High |
| **Semantic-Cache-Aware Routing** | Cost on repeat traffic | 30–95% (hit-rate dependent) | -200 to +5 ms | Medium |
| **Static / rule-based** | Predictable, zero-overhead | 0–30% | < 1 ms | Trivial |
| **LLM-as-classifier** | Semantic routing for ambiguous traffic | Variable | +100–800 ms | Low |

### The four SLO tiers

| Tier | Latency budget | Cost ceiling | Model pool |
|---|---|---|---|
| Realtime | < 500 ms | $0.001/req | Haiku, GPT-4o Mini, Gemini Flash-Lite |
| Standard | < 3 s | $0.01/req | Sonnet, GPT-4o |
| Premium | < 30 s | $0.10/req | Opus, o3, Claude Mythos |
| Batch | hours | $0.001/token | Local Llama, DeepSeek |

### The model tier table

| Tier | Examples | Input $ / M tok | Strengths |
|---|---|---|---|
| Nano/Flash | GPT-4o Mini, Gemini Flash-Lite, Claude Haiku | $0.07–$0.30 | Speed, cost, simple tasks |
| Standard | Sonnet, GPT-4o | $1–$5 | Balanced |
| Premium | Opus, Claude Mythos, o3 | $5–$15 | Hardest tasks, multi-step reasoning |
| Local | Llama, DeepSeek, Qwen | $0.001/token | Privacy, cost, throughput |

## The six routing patterns

| Pattern | Decision | Speed | Best for | Watch out for |
|---|---|---|---|---|
| **Rule-based** | Static rules (header, tag, file type) | < 1 ms | Explicit signals | Brittle, misses intent |
| **Semantic (embedding)** | Embed prompt, match to centroid | ~5–100 ms | Stable intent set | Cold start, centroid drift |
| **Intent-based** | Trained classifier (BERT, logreg) | 10–50 ms | Many stable routes | Label set maintenance |
| **LLM-based** | A model reads and picks | ~1 model call | Genuinely ambiguous, multi-intent | One extra model call |
| **Hierarchical** | Layered rules + embeddings + LLM | Combined | Production default | Complexity |
| **Auction-based** | Multiple candidates bid | 50–200 ms | Multi-objective Pareto | Hard to debug |

## The layered cascade (the production default)

A request hits a near-free rule check first, falls through to an embedding match if the signal is fuzzy, and only reaches the expensive LLM classifier if it is genuinely ambiguous. Most traffic resolves in the first two layers in milliseconds.

```
Request
  │
  ▼ 1. Rule check (< 1 ms)
   │ ──► high confidence? dispatch, done
   │ low confidence ▼
   │
   │ 2. Embedding match (~5 ms)
   │ ──► high similarity? dispatch, done
   │ low similarity ▼
   │
   │ 3. Semantic / ML classifier (50–100 ms)
   │ ──► confident? dispatch
   │ low confidence ▼
   │
   │ 4. LLM classifier (~1 model call)
   │ ──► confident? dispatch
   │ not confident ▼
   │ ask one clarifying question
```

## The cascade (cheap-first with escalation)

```
Query → Haiku → [confidence check]
  ├─ if high confidence: return response
  ├─ if low confidence: Sonnet → [confidence check]
  │     ├─ if high confidence: return response
  │     └─ if low confidence: Opus → return response
```

**Cascades pay a latency tax on the tail** (sequential calls) but eliminate the need for an accurate upfront complexity classifier. **Routing pays zero latency overhead** but requires a good predictor. ETH Zurich's 2024 paper "A Unified Approach to Routing and Cascading for LLMs" proves the theoretical optimality.

**Cascades are not interactive.** A two-escalation tail adds 600–900 ms. Fine for background agents; wrong for chat UIs.

## Speculative-Race (latency win)

Two models run in parallel on the same request. A verifier picks the better one. Cost is two inferences per request, but user-perceived latency drops 30–60% vs a serial cascade. Best for interactive UIs.

## Routing decision cost

| Decision type | Latency |
|---|---|
| Static / rule | < 1 ms |
| Embedding-based | 5–15 ms |
| BERT classifier | 10–50 ms |
| LLM-based classifier (Haiku) | 200–800 ms |
| Cascade escalation | adds full model roundtrip per escalation |

For sub-500 ms SLOs, only embedding or BERT classifiers are viable. For sub-200 ms, pre-classify at request ingress or use rule-based heuristics (query length + keyword patterns).

## Production rate limit management

- **Dual-bucket accounting**: track both RPM and TPM. A large prompt may not exceed RPM but will eat disproportionate TPM budget.
- **Exponential backoff with jitter** (±25%) to spread retry load.
- **Cross-key load balancing** across multiple API keys for the same provider, with real-time health tracking.
- **Cross-region routing** where the provider allows it (each region has independent rate limits).

## The capability registry

A structured record of what each model in your fleet supports. Enforce capability filtering before routing. Capabilities: context window, max output tokens, tool support, vision support, JSON-mode / structured output, system prompt length, system role support.

## Monitoring the routing stack

- **Routing decision distribution** — what fraction of requests go to each model.
- **Per-route output quality** — LLM-as-judge score or task-specific metric.
- **End-to-end latency per route** — p50, p95, p99.
- **Error rate per model**.
- **Fallback trigger rate** — how often the cascade escalated.
- **Cost per task type**.

A realistic budget estimate: apply a 1.7× multiplier on base token costs for 25% usage growth, 30% infrastructure overhead (orchestration, monitoring, failover), and 15% experimentation budget for new models.

## The five-step implementation order

1. **Instrument the existing gateway.** Per-request: input tokens, output tokens, latency, cost, destination model, quality proxy (verifier score, user feedback, judge rating). Two weeks of clean logs > two months of optimization on bad data.
2. **Add a semantic cache for internal traffic.** Internal tools have 40–70% repetition. Semantic cache pays back in the first week. Start with 24-hour TTL and 0.95 cosine-similarity; tune.
3. **Implement a single-router baseline.** A RouteLLM-style matrix-factorization router with two destinations (cheap + strong) is 40–60% cost reduction on most traffic. Easiest to debug.
4. **Layer a cascade on batch and background routes.** A three-tier cascade with a cheap verifier is 30–50% additional cost reduction. Do not put cascades on interactive routes.
5. **Build the second and third routers for MoR.** Once the single router is calibrated, train a latency-router and an accuracy-router. The aggregator starts as a weighted vote and evolves to per-request weighting.

## Verification

- **Calibration** — the routing classifier's confidence should match its actual accuracy. Plot a reliability diagram.
- **Cost per task type** — track separately; some tasks are inherently expensive.
- **Quality per route** — measure with an LLM-as-judge on a 5% sample.
- **Cascade escalation rate** — should be < 30% for most workloads; > 50% means the cheap model is too cheap.
- **p95 latency per route** — should match the SLO tier.
- **Cache hit rate** — semantic cache should hit 30–70% on internal traffic.

## Gotchas

- **Static routing has a place.** Don't over-engineer. Start with rules; add embedding only when rules can't keep up.
- **A 25% misroute rate exceeds the savings.** The classifier is the wrong model. Re-train or escalate.
- **Cascades are not interactive.** Use for background workloads only.
- **Self-preference bias in the routing judge.** Rotate the judge across model families.
- **A 1.7× budget multiplier is realistic, not pessimistic.** Add 30% for orchestration and 15% for experimentation.
- **Don't put caches in front of a model that does stochastic exploration** (e.g., creative writing). Hit rate is the wrong metric.
- **The cascade confidence threshold needs calibration.** A 0.7 confidence threshold calibrated on 100 examples is more reliable than a 0.9 threshold you guessed.
- **Cross-region routing is not free.** Some providers charge differently per region.
- **Refresh tokens and rate limits are coupled.** A 401 can cascade into a re-auth storm if not handled with jitter.

## Related

- `documentation/docs/policies/patterns/agent-cost-optimization.md` — the four cost levers
- `documentation/docs/policies/patterns/multi-agent-orchestration.md` — when to route between agents
- `documentation/docs/policies/patterns/prompt-caching-2026.md` — caching as a routing-adjacent lever
- `documentation/docs/policies/patterns/agent-eval-2026.md` — measuring routing quality
- `documentation/docs/policies/cloudflare/ai-gateway-best-practices.md` — gateway-level routing

## Source URLs (verified 2026-08-09)

- "AI Agent Model Routing and Dynamic Model Selection Strategies" (zylos) — https://zylos.ai/research/2026-03-02-ai-agent-model-routing/
- "Intelligent LLM Routing: Cost & Quality-Aware Selection" (Truefoundry) — https://www.truefoundry.com/blog/llm-routing-cost-quality-aware-model-selection
- "AI Agent Routing Patterns Explained: 2026 Guide" (Taskade) — https://www.taskade.com/blog/ai-agent-routing-patterns
- "Mixture-of-Routers and 2026 LLM Routing Techniques" (swfte) — https://www.swfte.com/blog/mixture-of-routers-llm-routing-techniques-2026
- "Multi-Model Agent Orchestration: Routing, Fallback, and Selection" (zylos) — https://zylos.ai/research/2026-06-27-multi-model-agent-orchestration-routing-fallback-selection/
- RouteLLM (ETH Zurich 2024) — https://github.com/lm-sys/RouteLLM
