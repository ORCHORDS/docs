# test-impact-analysis-ci

**Issue:** As a codebase grows past a few hundred tests, every pull request re-runs the entire suite even when the change touches one module, so CI time balloons from seconds to an hour, developers stop waiting for checks, and batch sizes grow to dodge the pain. Test impact analysis (TIA) solves this by maintaining a map of which tests exercise which production sources (historically built from coverage data) and running only the tests affected by the files that changed. Done naively, TIA silently skips tests whose dependencies are invisible to the mapping (dynamic imports, runtime config, shared fixtures, flag-gated code paths) and lets real regressions merge; done well, it cuts CI wall time 60-90 percent with a safety net of scheduled full runs. The engineering problem is selecting tests correctly, keeping the impact map fresh, and knowing when TIA is the wrong tool compared with predictive test selection or plain sharding.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How impact mapping works

1. **Coverage-derived maps.** The most common approach runs the suite once with per-test coverage collection (V8 coverage or istanbul), records which source files each test executes, and persists that test-to-source map as a build artifact. On later commits, diff the changed files against the map and schedule only the matching tests. Datadog CI Visibility, Gradle Enterprise, and Bazel's test target graph all institutionalize this pattern.
2. **Static dependency graphs.** For languages with reliable module resolution (Go packages, Bazel targets, Nx projects), a static import graph can replace coverage and stays correct even for tests that fail to run. This is faster and has no staleness problem, but it over-selects because it cannot distinguish which branches inside a module a test actually exercises.
3. **Native runner selection.** Before building custom infrastructure, use what the runner already gives you: Jest/Vitest's findRelatedTests plus changedSince against the merge base, Nx affected, Turbo affected, or Go test caching. Many teams discover these get 70 percent of the benefit with none of the maintenance burden of a homegrown map.
4. **Monorepo-aware diffing.** Always compute the diff against the true merge base of the PR branch and main, not the last commit, and map path prefixes to projects before selecting tests. Selecting from a wrong base either re-runs everything or skips tests that a rebased change affects.

## Failure modes that skip real bugs

1. **Invisible dependencies.** Dynamic imports, string-based dispatch, reflection, side-effectful module init, and runtime feature flags create edges the map never sees. A flag flip changes behavior without changing any watched source file, so TIA-based selection runs zero tests. Treat flag config files as universal dependencies that trigger the full suite.
2. **Shared fixture and library drift.** When a helper in a shared test-utils package changes, every test importing it is affected, but if the map only tracks production sources the transitive effect is missed. Include test-support code in the graph or accept that utils changes run the full suite.
3. **Stale maps after refactors.** File renames and moves invalidate coverage-based mappings. Regenerate the map on main after every merge (not nightly), and treat "no tests selected" for a non-trivial diff as a pipeline error rather than a fast success.
4. **Non-deterministic coverage.** Tests that exercise different code paths run-to-run (random ports, time-sensitive branches, shuffle order) produce a map that under-records. Pin seeds and freeze time so coverage collection observes the same paths every build.

## Guardrails and verification

1. **Scheduled full runs.** Run the complete suite on a cron against main (hourly or per release) to catch anything selection missed, and alert on the delta between selected-run failures and full-run failures. This is the single most important guardrail; skip it and TIA failures surface in production instead.
2. **Merge-queue full execution.** Selected runs belong in PR feedback loops where latency matters; the merge queue should run the full (or sharded-full) suite so main never takes an unverified shortcut. This bounds the worst-case blast radius of a bad map to CI latency, not correctness of main.
3. **Selection telemetry.** Log per build: files changed, tests selected, tests skipped, map age. When a regression lands despite green PR checks, this audit trail tells you whether the map was stale, the dependency invisible, or the test genuinely absent.
4. **Coverage regression check.** Compare line coverage of the selected run against the full-suite baseline for the same diff. A selected run covering dramatically less of the changed code than the full run is the earliest signal that selection is wrong.

## TIA versus alternatives

1. **Predictive test selection (PTS).** PTS (Launchable, Meta's Sapienz lineage, Datadog's predictive paths) uses ML on historical failure data to rank tests by likelihood of catching a bug, trading a small known miss rate for speed; TIA is sound-by-construction but conservative. CloudBees' 2025 comparison frames it as: TIA when you cannot tolerate missed tests, PTS when flakiness and history show most tests never fail.
2. **Sharding as the baseline.** Parallel sharding across machines (already covered in ci-test-parallelization) gives a linear speedup with zero selection risk. Measure first: if a fully sharded suite meets your latency budget, adding TIA only buys compute savings, not developer time.
3. **Mutation-scoped quality checks.** When combining with mutation testing, scope Stryker's --mutate argument to the same affected file set so slow mutation runs also shrink with PR size instead of running only on nightly jobs.
4. **When not to use TIA.** Small suites (< a few hundred tests, under 10 minutes fully parallel), heavily interdependent code where nearly every change selects most tests, or codebases with unreliable coverage tooling all get complexity without payoff. In those cases fix suite health first, selection second.
