# flaky-tests-destroy-ci-trust

**Issue:** A test suite that fails randomly trains the team to ignore CI. Within a quarter, "just re-run it" becomes the standard response to a red build, and then a real regression sails through on the fourth retry of a pipeline nobody read. This article captures the failure pattern, the measured costs (2025-2026 industry data puts flaky-test fallout at ~8% of total development time, roughly $120k per team per year, with ~36% of developers reporting monthly release delays from unreliable test failures), and the disciplines that keep a suite trustworthy.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the failure unfolds

1. **One test flakes, one engineer retries.** A timing-dependent test fails on a slow CI runner; the engineer re-runs the job, it passes, everyone moves on. No issue is filed, no failure is recorded, and the suite's first lie is told. Every subsequent failure is now plausibly a lie too.
2. **Retry becomes muscle memory, then policy.** "Just re-run it" spreads by imitation until someone configures automatic retries on the CI job — at which point flakiness is institutionalized. 2025 CI data shows ~47% of manually restarted failed jobs succeed on retry, which means half the red builds were noise, and half were signal the team just retried away.
3. **Red stops meaning anything.** Once a double-digit share of failures are false, engineers stop reading logs and start pattern-matching ("oh, that one always fails"). The 2026 flaky-test benchmark literature ranks time waste as the number-one negative effect, but lost trust is the mechanism that makes the time waste fatal: debugging effort drops to zero because nobody believes the failure.
4. **A real regression gets retried into production.** The predictable end state: a genuine failure looks exactly like the eleven false ones before it, someone hits retry twice, it passes by coincidence (ordering, caching, timing), and the bug ships. The postmortem finds the CI pipeline actually caught it — twice.
5. **The suite gets bypassed entirely.** Under deadline pressure, teams start merging with skipped suites or red-but-known builds, and the "required status check" gets disabled "temporarily". The safety net is now fully detached, and every future green build is theater.

## Root causes of flakiness

1. **Shared mutable state between tests.** Tests that touch the same database rows, files, environment variables, or singleton services produce order-dependent results: pass alone, fail in combination, fail differently when parallelized. Each test must own or reset its state.
2. **Time and network dependence.** `sleep(1)`-style waits, wall-clock reads, live network calls, and container race conditions fail exactly when CI machines are loaded — i.e., always at the worst moment. Inject a fake clock and a fake network; never let a unit test depend on either.
3. **Concurrency bugs in the product, misread as test bugs.** A meaningful fraction of "flaky tests" are real race conditions in the code under test, surfacing only under the scheduling jitter CI provides. Treat every flake as a potential product bug until proven otherwise — the flake is often the only repro you will ever get.
4. **Asynchronous assertions without polling.** Asserting immediately after triggering async work (checking a DB row before the write lands) yields failures that vanish on retry. Use proper wait-for-condition primitives with timeouts rather than fixed sleeps or instant asserts.
5. **Environmental drift between runs.** Different runner images, stale caches, leftover containers from a previous job, and daylight-saving/timezone differences on the host make "same code, different result" routine. Pin the CI environment as tightly as the code.

## What to do instead

1. **Detect flakes with repetition, not vibes.** Run the suite (or changed tests) N times per commit in CI — a test that passes 10 of 10 runs locally but 7 of 10 in CI is flaky, and that number belongs in a dashboard. You cannot manage what you do not measure.
2. **Quarantine with a budget and an expiry.** Move confirmed flakes to a quarantined track that does not block merges, but cap quarantine at ~5% of the suite (industry guidance treats >10% as a systemic design problem) and give every quarantined test an owner and a fix deadline. Quarantine without expiry is just deletion with extra steps.
3. **Fix the class, not the instance.** When a flake is diagnosed, grep for the pattern (shared fixture, sleep, live call) across the whole suite and fix all occurrences. Fixing one test at a time loses the race against copy-paste.
4. **Make retries observable, never silent.** If you allow automatic retries, the pipeline must report "passed on retry" loudly and count it against a flakiness budget. A retry that hides the original failure destroys the only data point that could have driven a fix.
5. **Treat new flakiness as a build-breaking event.** A test that was deterministic last week and is now flaky was changed by something this week — bisect it like a regression, because it is one. The alternative is normalizing the decay one test at a time.

## Metrics that keep the suite honest

1. **Flake rate per 1,000 runs.** The base frequency of pass-fail-pass sequences on identical commits; track it as a trend line, not a snapshot, and alarm on upward movement.
2. **Percentage of red builds that pass on retry.** This is your "CI is crying wolf" ratio. Above ~10%, engineers have already stopped reading failures whether management knows it or not.
3. **Median quarantine age.** How long quarantined tests sit unfixed. An age measured in months predicts the quarantine is a graveyard; measure in days predicts a healthy team.
4. **Time-to-trust: median engineer response to a red build.** When this drifts from "reads the log" to "hits retry", the social damage is done even if the technical metrics look flat.
5. **Determinism of the critical path.** The smoke/e2e tests that gate releases deserve their own stricter bar — effectively zero tolerance — because a flaky release gate is a security hole in your delivery process, not an inconvenience.
