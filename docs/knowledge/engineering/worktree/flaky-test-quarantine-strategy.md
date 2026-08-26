# flaky-test-quarantine-strategy

**Issue:** CI is green sometimes. A test suite of 3,000 tests fails 5% of the time with a different test each run, so engineers have learned to hit "re-run jobs" on red builds instead of reading failures. Real regressions now slip through because nobody trusts a red build — the flakiness has converted the entire test suite into noise, and merge queues slow down as everyone re-runs everything twice.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Detection before everything else

1. **Measure the flakiness rate first.** Google's published data: about 16% of their tests exhibit flakiness, and one in seven tests occasionally fails without a code change. You cannot manage what you have not counted — instrument failure-without-code-change detection before writing policy.
2. **Detect automatically via rerun deltas.** The core signal is a test that fails on one run and passes on an identical retry (same commit, same environment). Tools include GitHub Actions' flaky-test annotations, Datadog CI Visibility, BuildPulse, and CircleCI test-insights; in-house, a nightly job that runs the suite twice and diffs the results works.
3. **Never "mask" flakiness with blanket duplicate runs.** Running the whole suite twice on every PR doubles CI cost and hides the signal. Google explicitly discourages duplicate identical runs as a mitigation; detection must be surgical (rerun failures only).
4. **Tag, don't argue.** When a test is flagged flaky, mark it in code (`@flaky`, quarantine list, or CI annotation) with the detection data attached. The debate about whether it is "really flaky" ends when two runs of the same commit disagree.

## Quarantine mechanics

1. **Move flaky tests to a non-blocking suite, visibly.** Quarantined tests still run (scheduled job, separate CI lane) and report, but cannot block merges. Silently deleting or skipping them loses coverage you did not know you had; silently keeping them blocking destroys trust.
2. **Every quarantined test gets an owner and a deadline.** 14–30 days is the working window: an owner (person, not team), a linked ticket, and an expiry date in the quarantine entry. A quarantine without an expiry date is a graveyard.
3. **Cap the quarantine budget.** Set a hard limit (for example, quarantined tests must stay under 1% of the suite). When the cap is hit, the oldest entries are force-deleted or force-fixed — this prevents the queue from growing forever while everyone averts their eyes.
4. **Report the quarantine in CI output.** Merge-blocking lanes print "N tests quarantined, M days oldest entry" on every run; the number trending up is a visible health regression, trending down is visible progress.
5. **Quarantine the test, not the feature.** A flaky test often guards real behavior; the quarantine ticket must distinguish "test is broken" (fix the test) from "behavior is nondeterministic" (fix the product) — these have different owners.

## The fix-or-delete decision

1. **Expect most quarantined tests to resolve fast or never.** The ICSE 2024 Chrome study found 38% of flaky tests get fixed within 15 days of introduction, while 40% remain unresolved long-term. The practical implication: fix quickly after detection or delete; there is little middle band.
2. **Deletion is a legitimate outcome.** Google deletes roughly 16% of tests flagged flaky rather than fixing them — a reliably green suite is worth more than the marginal coverage of a test nobody trusts. Deleting feels like losing; shipping a test suite people re-run blindly is actually losing.
3. **Before deleting, ask what the test uniquely covered.** If deletion leaves a behavior with zero coverage, either write a replacement test that is deterministic or record the accepted coverage gap in the ticket. Delete-and-forget without this check is how regressions return.
4. **Fix the root cause, not the symptom.** The common root causes are shared mutable state between tests, real time and network dependencies, ordering dependence, and sleep-based waits replaced with proper synchronization (polling with timeout, deterministic clocks, per-test containers). Adding `time.sleep` or `--retry` inside the test is not a fix.
5. **Root-cause tooling pays for itself at scale.** Google's De-flake tooling locates the root cause of flaky tests in code with ~82% accuracy; even a simple "last green commit → first flaky commit" bisect report in the quarantine ticket cuts fix time substantially.

## Retry policy design

1. **Retry only failures, only in presubmit, and cap it.** Rerun just the failing tests, at most once or twice, and only on PR builds where the signal is "can this merge." This is Google's presubmit model: strategic reruns to keep authors unblocked, not blanket duplication.
2. **Never retry on main or scheduled runs.** Post-merge and nightly lanes must fail honestly — that is where flakiness gets detected and attributed. A main branch that auto-retries until green produces the appearance of reliability with none of the substance.
3. **A retry pass is a flakiness data point, not a pass.** Log "passed on retry" distinctly; tests that pass on retry more than once per quarter are quarantine candidates automatically.
4. **Block new flaky tests at the door.** Require new tests to pass N consecutive runs (2–3) before merge — cheap insurance versus the cost of removing established flakiness later.
5. **Beware the merge-queue interaction.** Retries inside merge queues compound badly: a 5% flaky rate across a long queue tank-queues legitimate PRs behind phantom failures. Merge queues do not fix flaky tests; flaky tests break merge queues.

## Health metrics

1. **Flaky rate: percent of red builds caused by flakiness rather than real regressions.** Target single digits; track weekly.
2. **Retry rate: share of PR builds that passed only after a rerun.** Rising retry rate is the earliest leading indicator of trust erosion.
3. **Quarantine age and size: oldest entry and total count.** Both should trend down after the program starts.
4. **Green-build trust proxy: how often engineers re-run red builds without reading the log.** Instrument the re-run button; when blind re-runs drop, trust is returning.

## Source URLs (verified 2026-08-15)

- https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html
- https://research.google/pubs/de-flake-your-tests-automatically-locating-root-causes-of-flaky-tests-in-code-at-google/
- https://dl.acm.org/doi/10.1145/3643656.3643899
- https://www.sciencedirect.com/science/article/pii/S0164121223002327
- https://testdino.com/blog/flaky-test-benchmark
