# local-model-eval-honesty

**Issue:** Three separate eval configurations reported numbers that flattered the local model and were wrong: an open-book eval (tool/lookup access allowed) scored 98% and got quoted as bare accuracy; a "fresh" eval turned out to share tasks with training data; and throughput was reported from warm-cache timing as if it were typical. Each lie had a different mechanism, and each was only caught because the number looked too good. This article records the dishonest patterns and the honest eval stack that replaced them, for the example project local-model program.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The evals that lied

1. **Open-book scores presented as closed-book.** With lookup/tool access the model hit 98% — but the number was reported without the access qualifier, implying knowledge the model doesn't have. An open-book eval measures retrieval-plus-reasoning, which is a different (and legitimate) quantity that must be labeled as such in every mention.
2. **Training-set leakage.** 52 of 111 "fresh" eval tasks were duplicates of training examples — the model was graded on memorized material. Mechanism, audit, and hash-registry fix are documented in `training-data-dedupe-freshness.md`; the rule here is that leakage is an EVAL design failure, not just a data-cleaning chore.
3. **Warm-cache timing as typical throughput.** Reporting tok/s measured after the model, KV cache, and file pages are hot understates what a user actually experiences. Cold and warm numbers differ by multiples; quoting only the warm one is a benchmark lie with no data bug anywhere in sight.
4. **Too-good numbers that went unchallenged.** Every lie above survived initially because high scores feel like progress. The standing rule since: a result far above the trendline (98% on a ~60% family) is a contamination flag until audited, not a win.
5. **Blended difficulty hiding regressions.** One aggregate score over mixed-difficulty tasks can hold steady while hard-task performance silently collapses; averages lie by omission.

## The honest eval stack

1. **Fresh-task single-shot rate as the headline.** The primary metric is: on tasks whose hashes are absent from all training registries, solved in ONE attempt, no retries, no hints. This is pass@1 on guaranteed-unseen tasks — the closest local analog to how a user experiences the model.
2. **Cold-start latency measured, separately.** Time-to-first-token from a genuinely cold process (model load, no cache priming) is reported alongside warm throughput, and the eval harness kills/starts the server per cold measurement rather than trusting one lucky first run.
3. **Tiered task difficulty with concrete anchors.** Tasks are binned easy/medium/hard by construction, not by vibe: easy = single-file single-concept fix; medium = multi-step with one interaction between concerns (e.g. a race plus its test update); hard = multi-constraint (e.g. behavior-preserving refactor under a perf budget). Every report shows per-tier solve rates, so a model can be honestly described as "easy 100% / medium 75% / hard 40%".
4. **Regression suites pinned to versions.** A frozen suite of tasks with fixed seeds, fixed graders, and fixed harness config is pinned per model version; before/after comparisons only run the same suite revision, and any suite change requires re-baselining. This is the local equivalent of the field's move to versioned, contamination-controlled benchmarks (SWE-bench Verified, SWE-bench Pro, SWE-rebench's continuous decontaminated collection).
5. **Retries reported separately from single-shot.** pass@k-style "any-of-k" numbers are useful (the unbiased estimator over n samples is standard), but they are a different metric and never averaged together with pass@1 — brute-force sampling inflates pass@k without making the model better, and mixing the two is how numbers drift upward.

## Contamination detection that scales locally

1. **Hash registry by construction.** The strongest defense is architectural: eval tasks are only scoreable if their hash is absent from the training registry — the harness hard-fails on collision (see `training-data-dedupe-freshness.md`). Detection after the fact is the fallback, not the plan.
2. **N-gram and MinHash similarity checks on top.** The literature's standard detectors (n-gram overlap, MinHash/similarity-based matching; see survey work like "Investigating Data Contamination in Modern Benchmarks") catch near-duplicates the hash misses; a weekly scan of eval-vs-train similarity is cheap insurance.
3. **Generate evals after the generator changes.** Fresh eval instances are generated per round rather than accumulated, the same motivation as SWE-MERA's dynamic benchmark and SWE-rebench's continuous collection — static public benchmarks rot because models train on them.
4. **Hold out a never-trained family.** One task family is permanently excluded from training; its solve rate is the cleanest generalization signal available, because no amount of within-family leakage can touch it.
5. **Log the access level with every score.** Every stored result carries metadata: open/closed-book, tool access on/off, temperature, attempt count, cache state. A number without its conditions is not a result, it's a rumor.

## Reporting rules

1. **One number per claim, conditions attached.** "98% fresh single-shot, closed-book, 0 registry collisions" — qualifiers travel with the number into every doc, standup, and commit message where it appears.
2. **Report the denominator.** "32/32 on unseen r4 tasks" says the sample; "98%" alone hides that it might be 98% of 3 tasks. Small-n results are flagged as small-n.
3. **Both cache states, always.** Throughput claims include cold-start latency and warm steady-state together; either alone is cherry-picking.
4. **Regressions before improvements.** Reports lead with any per-tier or per-family regression, then improvements — the reader needs the bad news first to correctly discount the good news.
5. **Pin versions in the claim.** Model hash + eval-suite revision + harness commit: an unpinned benchmark claim cannot be reproduced later, so it cannot be refuted either — which makes it worthless as evidence.

## Related

- `training-data-dedupe-freshness.md` (the leakage audit and hash-registry protocol)
- `star-task-family-design.md` (difficulty tiers and per-family solve rates)
- `ml-experiment-reproducibility-evidence.md` (version pinning discipline)
- `ai-cold-start-patterns.md` (cold vs warm infrastructure behavior)
