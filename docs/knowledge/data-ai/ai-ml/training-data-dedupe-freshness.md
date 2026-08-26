# training-data-dedupe-freshness

**Issue:** An STaR/self-improvement training round reported a 98% "fresh solve" rate — until auditing the dataset revealed 52 of 111 task pairs were DUPLICATES of training examples. The model was being graded on questions it had memorized. The number was fake and nearly shipped as a progress claim. Found in example project-1 v2 dataset.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the fake number happens

1. **Generation drifts toward duplication** — sampled tasks cluster around the generator's mode; near-identical tasks slip in without an exact-match check.
2. **"Fresh" is asserted, not verified** — the harness labeled tasks new because they were newly generated, not because they were distant from training data.
3. **Near-dupes evade exact matching** — renamed variables, reordered steps, or changed literals produce semantically identical tasks with different bytes.
4. **High scores feel like progress** — nobody audits the winner; the 98% would have been reported upward and believed.
5. **Eval and train share a distribution** — even non-duplicate evals drawn from the same generator overstate generalization.

## The fixes that made numbers real

1. **Dedupe BEFORE training** — normalize (strip whitespace/casing, canonicalize identifiers where feasible), then hash; reject both exact and near-duplicate matches against the existing corpus.
2. **Hash-registry for eval tasks** — every eval task's hash is recorded; a generated task colliding with the registry is regenerable, never gradable.
3. **Guarantee freshness by construction** — the eval harness must refuse to score any task whose hash family appears in training data, hard-fail rather than warn.
4. **Report the audit with the score** — "98% fresh" is only meaningful next to "0/111 registry collisions, dedupe removed 52 candidates".
5. **Re-audit each round** — every new generation cycle re-introduces the risk; dedupe is a pipeline stage, not a one-time cleanup.

## Generalizable rules

1. **Any eval that can be contaminated will be** — assume contamination, prove otherwise.
2. **Near-duplicate detection beats exact matching** — semantic similarity or canonical-form hashing catches what string equality misses.
3. **Memorized tasks measure memory, not ability** — the fix is excluding them, not celebrating them.
4. **Suspiciously good results get audited first** — a 98% on a previously ~60% task family is a contamination flag until disproven.
5. **Make the registry part of the artifact** — the hash registry ships with the dataset so future rounds inherit the protection.

## Related

- `vram-budget-model-selection-math.md`
- `../lessons/flaky-tests-destroy-ci-trust.md` (metrics that lie)
