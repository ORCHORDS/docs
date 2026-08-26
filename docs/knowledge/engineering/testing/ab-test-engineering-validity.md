# ab-test-engineering-validity

**Issue:** Product wants to ship the new checkout flow because "the A/B test showed +3.2% conversion, p<0.05." Nobody checked whether the experiment was valid: the variants got unequal traffic (sample ratio mismatch), the assignment logic had a bug that sent returning users disproportionately to control, the flag flipped mid-exposure, and the metrics pipeline dropped events from one variant. An invalid experiment produces a confident wrong answer, which is worse than no experiment. This article covers the engineering side of experiment validity — assignment correctness, SRM detection, guardrail metrics, and test-infrastructure patterns — informed by Microsoft Research's SRM work (Kohavi et al.), DoorDash's 2025 engineering write-up on SRM, and industry practice showing SRM affects 6–10% of A/B tests.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Assignment and bucketing correctness

1. **Unit of diversion must be consistent end-to-end.** If assignment is by user ID but logging joins by anonymous session ID, the same human splits across variants and the analysis double-counts. Pick one unit (user, session, or request — user for most product experiments) and thread it through assignment, exposure logging, and metric computation identically.
2. **Hash-based bucketing, not `Math.random()`.** Assignment must be a pure function of (unit ID, experiment key, salt): `bucket = hash(salt + userId) % 10000`. This makes assignment idempotent (a user gets the same variant on every request), debuggable (you can compute any user's assignment offline), and testable (a unit test over known IDs asserts exact bucket output). `Math.random()` assignment is neither stable nor auditable and is a top cause of SRM.
3. **Test the assignment function like any other code.** A property-based test that hashes N random user IDs and asserts a uniform spread (chi-squared against the expected split), plus example tests at bucket boundaries (0, 4999, 5000 for a 50/50 split of 10,000 buckets), catches skew from bad hashing, modulo bias, and off-by-one boundary bugs before any traffic flows.
4. **Assignment must be mutually exclusive or explicitly layered across concurrent experiments.** Two experiments each splitting 50/50 that share a salt silently correlate their variants. Use a layering system (mutually exclusive layers, or orthogonal salts per experiment) and a unit test that asserts pairs of live experiments have independent assignment for a sample of users.
5. **Guarantee sticky assignment under concurrency.** Two simultaneous requests from one new user must resolve to the same variant — write-through to the assignment store with the hash-derived value as the source of truth, never last-write-wins random. Two requests creating the same assignment is the concurrency case every test suite should include explicitly (see the bug-finding canon on simultaneous resource creation).

## Sample ratio mismatch: the canary of invalidity

1. **SRM = observed variant counts differ statistically from the configured ratio.** Microsoft Research defines it precisely: run a chi-squared goodness-of-fit test of observed assignments against the configured split; a 50/50 test where 49.7%/50.3% is fine but 48.9%/51.1% across 200k users is a screaming siren. Per the industry numbers cited by Monetate and replicated by Microsoft, roughly 6–10% of real experiments have SRM — this is not a theoretical concern.
2. **SRM invalidates the result regardless of the p-value on the metric.** With broken randomization, every downstream statistic is biased in an unknown direction; the +3.2% is uninterpretable. DoorDash's engineering write-up calls SRM one of the most egregious data quality issues precisely because the analysis pipeline will happily report significance on a broken experiment. Rule: analysis tooling refuses to display lift for experiments failing SRM.
3. **Automate the SRM check as a continuous test, not a post-hoc review.** Compute the chi-squared test on assignment counts as a scheduled job per live experiment; alert the owner on p<0.001 (the stricter threshold avoids false alarms). This is effectively a production monitor for the experiment system itself.
4. **Hunt SRM causes in the usual suspects.** The documented causes: differential bot/filtering rules across variants, redirect losses (one variant redirects and drops the exposure log), caching that serves variant A's HTML to variant B users, serialized flag state that skips assignment for some units, and crashes/errors that abort logging on one code path only. Each of these is also a test case for the flag-delivery layer.
5. **Add SRM to the experiment-creation checklist as a gate before ramping.** Run the experiment at 1% traffic for a day, check SRM on assignment counts (a small-ramp SRM check catches assignment bugs before they burn a week of 50% traffic), then ramp. The 1% canary is to experiments what a smoke test is to a deploy.

## Guardrail metrics and automated validity checks

1. **Every experiment ships with guardrail metrics that must not move.** Latency p75, error rate, crash rate, checkout completion, support-ticket rate — metrics where the organization has strong priors about what "broken" looks like. Guardrails run alongside the OEC (overall evaluation criterion) and auto-trigger a halt when breached; Statsig, GrowthBook, and LaunchDarkly all support this natively in 2025-era stacks.
2. **Make "did the treatment break instrumentation" a first-class check.** Differential logging — the treatment path fails to emit an event the control path emits — shows up as SRM or as spurious metric drops. A contract test asserting both variants emit the same event schema on the same user journey catches this pre-launch (the event-schema variant of `api-mock-fidelity-schema-locking.md`).
3. **Alert on sample size vs expected enrollment.** If the experiment enrolls 30% fewer units than the traffic model predicts, exposure logging is broken even if the ratio happens to match; expected-N with a tolerance band is a cheap, high-yield monitor.
4. **Log exposure events at the moment of assignment, atomically with the assignment decision.** Exposure logged on first metric event instead of at assignment creates survivorship bias (users who bounce before the metric fires are never counted in one variant differently than the other) — one of DoorDash's listed SRM mechanisms.

## Testing the experimentation system itself

1. **Treat the flag/assignment service as critical-path code with its own test suite.** Unit tests on bucketing math and boundary conditions, integration tests on sticky assignment and concurrency, and a synthetic canary that hashes a fixed panel of user IDs every N minutes and alerts if any assignment flips — the production-facing equivalent of a golden-file test (`golden-master-testing.md`).
2. **Integration-test the full pipeline with a seeded experiment.** A fixed cohort of synthetic users, a known assignment outcome, injected metric events, and an assertion on the computed lift and SRM p-value exercises assignment, exposure logging, ingestion, and analysis end-to-end; this catches the class of bug where each component passes in isolation but the join is wrong.
3. **Simulate SRM conditions deliberately.** Test the SRM detector itself by injecting experiments with skewed assignment (drop 3% of one variant's logs) and assert the monitor fires; a validity checker that has never been tested against a known-invalid experiment is decoration.
4. **Test ramp-down and kill-switch behavior under load.** The kill switch must disable a variant without re-bucketing users or losing assignment history; a load test that flips the switch mid-traffic and asserts no assignment churn and no dropped events verifies the scariest operational path.

## Related

- `event-driven-testing.md` — testing the event pipeline that exposure and metric logging ride on
- `golden-master-testing.md` — golden outputs for the synthetic assignment panel
- `flaky-test-detection.md` — statistics of variance that SRM checks borrow
- `workers-test-patterns.md` — where assignment logic lives in this repo's edge tier
