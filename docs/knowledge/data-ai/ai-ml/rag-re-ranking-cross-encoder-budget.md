# RAG Re-Ranking Cross-Encoder Budget

First-stage retrieval is built to be fast and forgiving: fetch a few hundred plausible candidates, accept imperfection. Re-ranking exists to convert that breadth into a precise top handful — a cross-encoder scores each query–passage pair jointly and ranks far better than bi-encoder similarity can. The catch is arithmetic: cross-encoders are expensive per pair, and the cost multiplies by candidate depth. Re-ranker design is fundamentally budget engineering — choosing depth, models, and caching so that precision gains arrive before latency and cost do.

## Scope

This article covers re-ranking stage design in RAG pipelines: cross-encoder mechanics and why they outscore bi-encoders, the depth-versus-cost trade, latency budgeting, model-tier choices, and cache integration. It applies to retrieval systems adding or operating a re-rank stage.

Excluded: first-stage retrieval and fusion (the prior stage), generation-side context selection once the final set is chosen, and training custom rerankers (model development with different economics).

The trade in numbers you must compute, not feel: scoring K candidates costs K forward passes of a model typically far larger than an embedding model. Doubling candidate depth doubles re-rank cost and latency while usually adding single-digit-percent recall of good material near the top. The optimal depth is discovered by sweep, and it is almost always shallower than intuition suggests.

## Workflow or implementation guidance

1. **Establish the first-stage baseline before adding the stage.** Measure answer quality and top-K precision without re-ranking. If first-stage precision at your working K is already high, the reranker buys little; if it is low, fix retrieval or chunking first — rerankers polish candidates, they cannot recover documents never retrieved. The baseline also prices the improvement: gains are only real relative to a measured incumbent.
2. **Sweep depth against quality, then set depth per traffic class.** For K in (25, 50, 100, 200...), measure end-task quality and top-K precision on the evaluation set. Quality typically saturates quickly; pick the shallowest K within noise of the best. Identifier-heavy or homogeneous corpora saturate earlier; diverse or multi-aspect traffic may justify deeper fetching. One global depth is a compromise — per-class depth captures the difference.
3. **Pick the model tier by the latency budget, not leaderboard rank.** Rerankers range from distilled small cross-encoders to large multi-billion-parameter models. The budget question comes first: at your QPS and K, what per-request re-rank latency and cost can the product tolerate? Choose the strongest model that fits; the accuracy difference between adjacent tiers is usually smaller than the latency difference.
4. **Bound and parallelize the stage.** Re-rank compute parallelizes across candidates; batch candidates into a single or few inference calls where the serving stack supports it. Set hard stage deadlines: if re-ranking exceeds its budget (queueing, degraded replicas), degrade gracefully to first-stage order rather than stalling the request. Graceful degradation is a designed path, tested in drills.
5. **Cache re-rank results for repeated query-passage pairs.** Popular passages re-appear across similar queries; a bounded cache keyed on (query hash, passage hash, model version) returns prior scores without recompute. Like all caches in this family, the key must include the model version or an upgrade silently serves stale rankings.
6. **Log the reorder delta.** Record how much the reranker changed the delivered order (rank displacement of delivered passages). Shrinking deltas mean the first stage improved or the reranker is becoming redundant; growing deltas on a class mean first-stage quality slipped there. The delta is the stage's own health metric.

## Controls

- **Stage latency SLO and deadline enforcement.** p95/p99 re-rank latency with a hard timeout that falls back to first-stage ordering; timeout rate is alarmed.
- **Depth configuration governance.** Candidate depth is versioned, per-traffic-class configuration; changes require sweep evidence attached, mirroring model-promotion discipline.
- **Cache correctness.** Model version in every cache key; cache hit-rate and staleness metrics; invalidation on model change verified by a canary query set.
- **Quality regression gate.** The evaluation harness (recall/precision at operating K plus end-task quality) runs on any reranker model or depth change; regression blocks promotion.
- **Cost telemetry per stage.** Re-rank cost isolated from embedding and generation cost in accounting, so the stage's economics stay visible as traffic grows.

## Validation evidence

- Depth-sweep curves on the evaluation set: top-K precision and end-task quality versus K, with the chosen operating point and its saturation justification documented.
- Tier comparison: candidate models at the chosen depth, quality and measured latency/cost side by side, with the tier selected under the stated budget.
- Degradation drill results: stage deadline exceeded under injected load; fallback engaged; end-to-end latency held; delivered quality degraded gracefully and measurably.
- Cache economics: measured hit rate on production query distribution, cost saved versus cache operational cost, and post-upgrade canary evidence proving stale-key invalidation worked.

## Failure modes and correction

- **Depth bloat.** "More candidates can't hurt" — except it doubles cost and adds latency while the sweep shows saturation long before. Correction: depth is set by sweep evidence per class; global depth increases need cost justification attached.
- **Tail-latency blowout.** Mean re-rank latency is fine; p99 explodes when a burst of long passages hits the cross-encoder. Correction: per-request passage-length caps (truncate for scoring, deliver full text), stage deadlines, and per-class depth so latency-critical classes run shallow.
- **Stale cache after model upgrade.** New reranker, same cache keys: old scores served under the new model's name. Correction: model version in the key (choke-point implementation); upgrade runbook includes cache flush plus canary verification.
- **Reranker papering over retrieval rot.** First-stage recall degrades (embedding drift, index staleness); the reranker still polishes whatever arrives, delivered quality slides, and the stage's delta log grows. Correction: monitor the reorder delta alongside first-stage recall; investigate first-stage metrics when delta grows.
- **Graceful degradation never tested.** The fallback path exists in code and fails in production on first use (schema mismatch, timeout bug). Correction: degradation drills in the deployment checklist; fallback is exercised, not assumed.

## Limitations

Optimal depth and tier are corpus- and query-mix-dependent and shift with first-stage quality; conclusions here require re-derivation after retrieval changes. Cross-encoder latency characteristics vary substantially across hardware and serving stacks, so binding latency numbers come from measurement, not documentation. Listwise and LLM-based rerankers change the cost structure (one call over the whole list rather than per-pair scoring) and need their own sweeps. This article covers the re-rank stage in isolation; multi-stage cascades (cheap filter, strong rerank) and learned routing between stages extend the same principles but add interactions not treated here.

## Canonical sources

- Cohere documentation, Rerank: https://docs.cohere.com/docs/rerank-overview
- Sentence-Transformers documentation, Cross-Encoders: https://sbert.net/docs/sentence_transformer/usage/semantic_search.html#cross-encoders
