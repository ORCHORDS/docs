# mutation-testing-survivor-triage

**Issue:** The team ran Stryker (see `mutation-testing-stryker.md` for setup), got a mutation score of 61%, and now a 4,000-row report of surviving mutants sits unopened — nobody knows which survivors mean "missing test," which are unkillable equivalent mutants, or how to afford running this in CI. This article covers the interpretive and operational half: reading the report, triaging survivors, handling equivalent mutants, and making mutation runs cheap enough to actually gate PRs. Informed by Stryker's equivalent-mutants documentation, 2025 research on mutant prioritization (arXiv 2505.05584) and GenAI-assisted triage, and the mutation-testing literature on equivalent-mutant ratios.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Reading a mutation report correctly

1. **Mutation score = killed / (total − equivalent), not killed / total.** The University of Luxembourg mutation-testing reference is explicit that equivalent mutants must be excluded from the denominator; a raw score that includes them understates quality and, per the 2025 ScienceDirect analysis, equivalent-mutant RATIO varies so much by codebase that comparing raw scores across projects is meaningless. Compare trends within one codebase only.
2. **A surviving mutant is a question, not a verdict.** It asks "if this line were wrong, would any test notice?" — the answer is sometimes "no test needs to" (logging, logging-format, cosmetic branches). Triage answers the question; it does not auto-generate tests.
3. **Read survivors clustered by file, not by score.** One file with 40 survivors and perTest coverage showing no test executes it is a coverage hole worth an afternoon; 40 scattered survivors across utility code is usually assertion weakness. Cluster first, then work the top 3 files.
4. **Distrust high scores with low perTest analysis.** Without `coverageAnalysis: "perTest"` Stryker runs the whole suite per mutant, both slow and less informative — with perTest, the report shows which test SHOULD have killed each mutant, which turns triage from archaeology into a todo list.
5. **Track "no coverage" mutants separately from "survived" mutants.** No-coverage means no test runs the line (a coverage problem, fixable mechanically); survived means tests ran and none cared (an assertion problem, needs judgment). Mixing them hides which disease you have.

## Triage workflow for survivors

1. **Classify every survivor into one of five buckets before writing anything:** missing test (behavior worth testing, none exists), weak assertion (test runs the code but asserts too little), unreachable/dead code (delete the code instead of testing it), equivalent (see next section), or not-worth-testing (logging, debug formatting — document and move on). The 2025 Tessl/Indium GenAI-triage tooling automates exactly this classification, returning per-mutant verdicts and priority scores.
2. **Fix weak assertions before adding tests.** If a test executes the mutated line and still passes, the cheapest kill is strengthening its `expect` — often one property check (`toHaveBeenCalledTimes`, field equality) kills a whole cluster of survivors in that function.
3. **Convert missing-test survivors into named test cases directly.** Each meaningful survivor is a ready-made test: assert the behavior that distinguishes mutated from original code. Stryker's perTest analysis tells you the nearest existing test file to put it in.
4. **Ratchet, don't boil the ocean.** Gate PRs on "no NEW survivors in changed lines" (Stryker's incremental diff) while the global score climbs slowly on a nightly schedule. A team that must clear 4,000 legacy survivors before merging will delete Stryker within a month.
5. **Prioritize by risk, and let machines do the sorting.** 2025 research (arXiv 2505.05584) shows prioritizing surviving mutants — by code criticality, churn, and kill-difficulty — before spending LLM/human effort on test generation significantly improves yield; triage payment-processing mutants before date-formatting ones.

## The equivalent mutant problem

1. **Definition: a mutant that produces observably identical behavior, so no test can ever kill it.** Classic examples: `x * 2` mutated to `x + x` (wait — that one IS equivalent), `x < y` vs `x <= y` when x ≠ y is guaranteed upstream, optimizations like loop-unrolling variants. Stryker's docs dedicate a page to these because they are the number-one reason teams chase impossible scores.
2. **Never write a test specifically to kill a suspected equivalent mutant.** You cannot distinguish it from the original by definition; attempting it wastes the exact effort triage exists to protect. Confirm equivalence by reasoning about the invariant, then mark and exclude.
3. **Use the standard exclusions rather than heroics.** Stryker/mutation-testing-elements lets you annotate mutants as ignored with a reason in the report; trivial compiler-equivalence techniques (TCE/TCE+ from the academic literature) can auto-detect some classes, but pragmatically most teams hand-annotate a small persistent ignore list with justifications.
4. **Reduce equivalent-mutant breeding grounds at the source.** Code that compares the same value twice, dead defensive branches, and duplicated logic generate disproportionate equivalents — refactoring them away often kills more "unfair" survivors than any testing effort, and the code gets better.
5. **Keep the ignore list small, reviewed, and versioned.** An unreviewed exclusion list silently becomes a way to inflate the score; each entry needs a reason string, and growth of the list should be visible in review just like `// eslint-disable`.

## Making mutation runs affordable in CI

1. **Run incrementally on PRs, fully on a schedule.** Mutation-test only changed files/lines on pull requests (Stryker incremental mode) so feedback lands in minutes; run the full suite nightly or weekly on a cron where a 45-minute run is fine. Full-suite-on-every-PR is why most adoption attempts die in week two.
2. **Constrain what you mutate.** Mutating generated code, type declarations, config, and vendored directories burns CI time for zero insight; an explicit `mutate` allowlist of business-logic globs (with `!exclusions`) keeps runs both fast and meaningful.
3. **Use perTest coverage analysis everywhere.** It is the single biggest speed lever: Stryker runs only the covering test(s) per mutant instead of the suite, typically an order-of-magnitude speedup, and it makes reports more actionable for free.
4. **Gate on the diff, not the global score.** PR fails if changed code introduces surviving mutants; the global mutation score is a trend metric on a dashboard, not a merge blocker. This matches how coverage gates actually survive contact with legacy code (see `jest-coverage-thresholds.md` for the coverage analog).
5. **Budget compute honestly.** A full run on a large repo can take an hour of CI; run it on a self-hosted/larger runner, cache Stryker's incremental state between runs, and delete the state only when dependencies change. Mutation testing that costs more than the bugs it finds gets turned off — measure that tradeoff once a quarter.

## Related

- `mutation-testing-stryker.md` — Stryker installation and configuration basics
- `test-coverage-meaningful-metrics.md` — why line coverage lies and mutation score supplements it
- `jest-coverage-thresholds.md` — the ratcheting-gate pattern mutation gates borrow
- `test-maintenance-strategies.md` — keeping the whole quality apparatus sustainable
