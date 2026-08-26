# model-cascade-cheap-first-routing

**Issue:** Teams route requests to one model chosen by a classifier or a vibe, which means every misroute is a silent quality loss or cost blowout with no recovery path. The alternative — a cascade — flips the risk: try the cheap model first, check whether its answer is good enough, and only escalate to the expensive model when it is not. The token-economics article covers intent-based upfront routing; this article covers the escalation pattern (FrugalGPT-style), how to judge "good enough" without paying for a human, and where cascades beat and lose to upfront routers.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The pattern

1. **Cheap-first, escalate on doubt.** Send every request to the cheap tier (local model or mini-class API). If the answer passes a cheap quality gate, return it; otherwise re-send to the next tier. FrugalGPT (Stanford) showed up to ~98% cost reduction on some benchmarks while matching GPT-4-quality answers; RouteLLM-class learned routers achieve similar quality at ~85% lower cost on arena-style evaluations.
2. **Cascade vs upfront router.** Upfront routing decides before generating (fast, one call, but errors are silent and unrecoverable). Cascades decide after the cheap attempt (adds one inference of latency and compute for the escalated minority, but mistakes self-correct). Cascades win when quality misses are expensive; routers win when latency budgets are tight.
3. **Tier selection matters more than the gate.** The cheap tier must be genuinely competent at the easy 70-80% of traffic; the quality gap between tiers sets how often you escalate. A too-weak cheap tier escalates so often you pay double (cheap attempt + flagship retry) on most requests.
4. **Add an exact-match cache in front of the cascade.** Repeated questions (FAQs, dashboards, agent retries) never hit any model. Cache hits are the cheapest tier of all and compound with every other cost lever.
5. **Combine with prompt caching for the escalation path.** When the flagship retries, the shared prefix (system + tools + context) reads from cache at ~10% input cost — the retry is cheaper than it looks, which justifies a more aggressive cheap-first policy.

## Judging "good enough" cheaply

1. **Confidence signals from the cheap model itself.** Token logprobs / entropy flag uncertainty; a low-probability answer or hedged phrasing ("I'm not sure", "cannot determine") is a cheap, no-extra-call escalation trigger. Not foolproof — poorly calibrated small models can be confidently wrong — so pair with one more signal.
2. **LLM judge as verifier.** A mid-tier model scores the cheap answer against the question on a 1-5 rubric (or binary "would you hand this to a customer?"). This is the FrugalGPT scoring approach and costs a fraction of a full regeneration. Keep the judge prompt tiny and cached.
3. **The "would recommend" verbatim trick.** Ask the judge to respond with a fixed token (e.g. "yes"/"no" or 1-5); single-token constrained scoring makes the judge call nearly free and its output trivially parseable.
4. **Task-specific verifiers beat generic judges where possible.** For extraction: validate against the schema. For code: compile/run tests. For math: check with a calculator/SymPy. Deterministic checks have no judge bias and cost nothing.
5. **Never let the cheap model grade itself.** Self-evaluation correlates with its own errors; the gate must be independent (logprobs + external check, or a different model judging).

## Tuning and pitfalls

1. **Set the escalation threshold from a golden set.** Label 100-200 real requests with acceptable/unacceptable answers, sweep the gate threshold, and pick the point where cost-per-correct-answer is minimized — write the number down and re-sweep when models change.
2. **Latency stacking is real.** The escalated minority pays cheap-attempt + judge + flagship latency. Cap cascades at 2 tiers in interactive paths and route known-hard categories directly to the top (a static bypass list is fine).
3. **Error propagation.** If the cheap tier's partial answer is passed to the flagship as context, garbage anchors the retry. Escalate with the ORIGINAL request plus (at most) the cheap attempt labeled as a rejected draft.
4. **Track the metrics that expose failure:** escalation rate (target the 20-40% band), double-cost rate, end-quality score, and p95 latency. An escalation rate near 0% means the cheap tier is doing everything (audit quality); near 100% means the cheap tier is decorative.
5. **Watch for cascades hiding model regressions.** A quietly degraded cheap tier just escalates more, cost creeps up, and nobody notices quality changed. Alert on escalation-rate drift, not just spend.
6. **Vendor routers exist if you do not want to own this.** RouteLLM (open-source learned routers), Martian, NotDiamond, Portkey-class gateways productize the decision — reasonable while calibrating, but own the eval set either way, because the router's optimization is not exactly yours.

## Anti-patterns

1. **Escalating on every hedging phrase** — cheap models hedge constantly; phrase-only gates push escalation to 80%+ and the cascade becomes a surcharge.
2. **Trusting the cheap model's self-reported confidence alone** — small models are often mis-calibrated; combine with an external check or judge.
3. **Unbounded cascade depth** — three-plus tiers multiply worst-case latency and debugging pain; two tiers plus a bypass list covers almost all real workloads.
4. **Judging answers with the same model that produced them** — correlated errors pass the gate and users meet the failure first.
