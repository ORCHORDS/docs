# feature-flag-testing-strategy

**Issue:** Feature flags ship incomplete code to production behind runtime switches, and every flag doubles the behavioral surface of the code it guards. Two flags interacting create four configurations; ten create over a thousand. Teams that test only the default flag state discover broken off-branches in production, while teams that try to test everything exhaustively drown. A deliberate strategy is needed: which states get tested at which level, how combinations are sampled, how flag state is controlled inside tests, and how flags and their dead code get cleaned up before they rot into permanent complexity.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## State coverage strategy

1. **Test both states of every flag against a stable baseline.** The minimum viable rule: each flag's on and off paths must be exercised by at least one automated test, so a broken branch cannot hide behind an untested switch. Unit and integration layers carry this load; end-to-end tests cover only the highest-risk flags in both states.
2. **Use pairwise sampling for combinations, not exhaustive 2-to-the-n.** Research consistently shows most interaction faults are exposed by covering every pair of flag values rather than every combination. With more than three live flags, generate a pairwise matrix (each pair of flags tested in all four on/off combinations across the suite) and accept the documented residual risk instead of pretending exhaustive coverage exists.
3. **Test the default state as production sees it.** The suite's default configuration must match what production evaluates for the general population; drift here means all untested-flag-path tests are silently validating a configuration that never ships.
4. **Cover flag evaluation edge values.** Rules like percentage rollouts, user-attribute targeting, and kill switches have boundaries (0 percent, 100 percent, matching user, non-matching user, missing attribute) that deserve explicit test cases, because evaluation bugs distribute traffic wrongly without failing loudly.

## Controlling flags inside tests

1. **Inject flag state through the test harness, not the user record.** Prefer a harness that forces flag values for the test's scope (context override, test-only provider, or an environment-backed evaluator) over mutating production targeting rules, which is slow, racy across parallel tests, and leaks state.
2. **Make flags part of the fixture.** Encode the flag configuration a test needs alongside its other setup so each test is explicit and independent; a test that depends on ambient flag state fails mysteriously when a default flips.
3. **Reset flag state between tests.** Flag services often cache evaluations; the teardown path must clear overrides and caches, or a later test inherits the previous test's configuration and fails only in certain orderings.
4. **Simulate evaluation-service failure.** When the flag provider is unreachable or times out, the application must fall back to a documented default. A test that blocks the provider connection and asserts the fallback behavior catches the worst class of outage: a flag outage taking the whole app down.
5. **Force flags in end-to-end tests via the provider's test API.** For UI tests, use the flag tool's forced evaluation (targeting a test user or a test key) rather than intercepting its network responses, so the app exercises its real evaluation path.

## Managing flag debt

1. **Keep live flag count small.** Every permanent flag multiplies test surface and review cost; a budget (for example, single-digit concurrent flags per service) forces cleanup conversations. DraftKings and LaunchDarkly guidance both converge on flag minimization as the first lever.
2. **Record an owner and expiry on every flag.** Metadata (creator, rollout plan, removal ticket) lets automation flag stale entries; a flag with no owner and no recent evaluation variance is a deletion candidate.
3. **Automate stale-flag detection.** Continuously evaluate flags against production traffic: a flag serving 100 percent or 0 percent of traffic for a sustained window has finished its rollout and should enter the removal queue automatically.
4. **Test the flag-removal commit like a behavior change.** Deleting a flag and its dead branch is a code change that can break the surviving path; run the suite with the dead branch removed, not just with the flag flipped, before deleting.
5. **Track removal in the definition of done.** The feature is not done when the flag is on for everyone; it is done when the flag no longer exists. Bake this into the rollout checklist so cleanup is planned work, not archaeology.

## Guardrails in CI

1. **Fail on untested flag branches.** Coverage tooling can attribute coverage per flag state; a diff that adds a flag branch with no test touching it should fail or at least warn in review.
2. **Run a flag-matrix job on schedule.** A nightly job that runs a core regression pack across a sampled set of flag combinations catches interaction breakage without paying the matrix cost on every commit.
3. **Snapshot the flag configuration per build.** Recording which flags and values a test run used makes failures reproducible months later, when defaults and rules have moved on.
4. **Alert on default drift.** If the suite's default flag configuration stops matching the production default, CI should say so explicitly rather than letting coverage silently shift to the wrong baseline.
