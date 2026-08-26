# star-task-family-design

**Issue:** STaR-style self-improvement (generate solutions, keep the ones that pass, fine-tune, repeat) stalled when run over ad-hoc random tasks — the model sharpened on whatever the generator's mode produced instead of broadening. The loop only produced real gains after tasks were organized into DESIGNED families, each with its own generator, its own machine-checkable success criterion, and fresh-task evaluation. Observed across example project STaR rounds r1-r4.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The senior-tier families that worked

1. **race-fix.** Tasks inject a concrete concurrency bug (shared mutable state, missing lock, check-then-act) into a small program; success = the seeded race is gone AND the original test suite still passes. Verifiable because the bug is seeded, so the fix is checkable by construction.
2. **error-taxonomy.** Tasks present a real error log harvested from actual runs and ask for a classification (e.g. race vs deadlock vs resource-leak vs config); success = exact match against the label assigned when the log was captured. Ground truth comes from provenance, not from a judge model.
3. **perf-budget.** Tasks pair a small hot function with a measurable budget (e.g. "must complete in < X ms on input size N"); success = measured wall-clock/CPU under the budget, no style opinions. Measurement, not vibes, is the filter.
4. **refactor-safe.** Tasks require a behavior-preserving refactor (extract function, kill duplication, rename across scope); success = the pinned test suite passes byte-identically before and after. The hardest family to fake and the best signal for senior-tier code sense.
5. **Common shape.** Every family is (a) generative — can emit unlimited fresh instances, (b) verifiable — a machine decides pass/fail with no LLM judge in the loop, and (c) difficulty-tunable — parameters (bug depth, budget tightness, refactor scope) dial the challenge.

## Why designed families beat random tasks

1. **Random tasks collapse to the mode.** Free-form task generation drifts toward the generator's favorite shapes (see diversity-collapse literature: Verbalized Sampling on mode collapse, SeDi-Instruct on diversity-based filtering). A family's parameter space forces spread the sampler won't produce on its own.
2. **Families make verification possible.** "Fix this bug" is only gradeable if the bug was seeded by the harness; a family bakes the grader into the generator. Random tasks leave you with an LLM judge, which is slower, driftable, and gameable.
3. **Families give a curriculum.** Difficulty knobs (race complexity, budget margin, refactor distance) let each round train near the model's edge — the STaR principle that you fine-tune on correct self-generated rationales, applied at the task level rather than the trace level.
4. **Families make failure diagnosable.** When a round regresses, per-family solve rates tell you WHICH capability regressed; a single blended number over random tasks tells you nothing actionable.
5. **Families resist eval contamination structurally.** Fresh instances are generated and hash-checked per round (see `training-data-dedupe-freshness.md`), and the family's parameter space is wide enough that a new instance is genuinely unseen even though the family is known.

## Family mechanics: generate, dedupe, evaluate

1. **Per-family generators.** Each family has a dedicated generator that samples parameters (bug type, input size, budget, refactor target) and emits task + grader as a pair — the grader never exists separately from the task.
2. **Hash-registry dedup as a pipeline stage.** Every generated instance is normalized and hashed against the registry of training AND eval tasks; collisions are regenerated, never admitted (full protocol in `training-data-dedupe-freshness.md`).
3. **Eval is fresh single-shot, never replay.** Scoring uses only tasks whose hashes are absent from all training rounds — the 32/32 result on unseen r4 tasks counts precisely because the harness would have refused to score a colliding task.
4. **Per-family solve-rate dashboard.** Each round reports solve rate by family and by difficulty tier; the headline number is the weighted blend, but regressions are caught family-first.
5. **Families retire.** When a family's fresh-task solve rate saturates (near-100% across difficulty tiers), it stops driving improvement and gets frozen as a regression guard rather than continuing to dominate training mix.

## Design rules for new families

1. **No verifier, no family.** If pass/fail cannot be decided by a seeded bug, a measurement, or a pinned test suite, the family is a prompt-collection, not a task family.
2. **Prefer provenance over judges.** error-taxonomy's labels come from how the log was captured; a judge model's opinion is a last resort and always logged as such.
3. **Require at least one difficulty knob.** A family with fixed difficulty trains one point, not a capability; saturation arrives immediately and the loop stalls.
4. **Seed from real artifacts.** Real error logs, real perf profiles, real refactor commits — real-world priors keep the distribution honest against the generator's imagination.
5. **Size the family to the gap.** Add families targeting observed weaknesses (e.g. concurrency was a known weak spot, hence race-fix first), not topics that are merely easy to generate.

## Related

- `training-data-dedupe-freshness.md` (hash registry, fresh-task guarantee)
- `local-model-eval-honesty.md` (how the fresh-task eval is scored honestly)
- `smart-merge-fleet-writes.md` (merging writes from parallel family trainers)
