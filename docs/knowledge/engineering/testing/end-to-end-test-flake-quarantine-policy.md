# End To End Test Flake Quarantine Policy

End-to-end tests exercise the whole stack: browser, network, server, database, third-party
service. That surface produces flakes — failures that are not caused by a defect in the
system under test but by transient conditions in any layer. A flake is not a defect, but an
unchecked flake erodes the credibility of the whole suite: every red build becomes a
candidate to be ignored, and a real regression hiding behind the noise is missed. The
quarantine policy is the discipline that distinguishes flakes from real failures: a documented
classification, a tracked set of quarantined tests, and an obligation to act on the
quarantine before it becomes permanent.

## Scope

Covers the policy that governs flaky end-to-end tests in a continuous-integration pipeline:
how flakes are identified, how they are recorded, how the suite behaves while a test is in
quarantine, and how the quarantine is cleared. Applies to E2E suites built on Playwright,
Cypress, or equivalent frameworks, and to the CI layer that orchestrates them. Does not
cover the engineering that prevents flakes in the first place (that is a separate discipline
covering waits, retries, isolation, and state management).

## Workflow or implementation guidance

1. **Distinguish flake from failure before acting.** A flake is a non-deterministic pass/fail
   result against unchanged code; a failure is a deterministic red against a code change.
   The CI layer should not auto-retry every failure into pass — that hides real bugs.
   Distinguish by retry-on-pass behaviour: a test that fails once and passes on retry, with
   no code change, is a flake candidate. A test that fails twice in succession is a real
   failure until proven otherwise.
2. **Quarantine, do not delete.** The temptation when a flake appears is to delete the test,
   on the grounds that a red build is worse than a missing test. Deletion is irreversible
   and the test was added for a reason. Quarantine moves the test out of the blocking set
   while leaving its assertions and history intact.
3. **Mark the test as quarantined at the source.** The Playwright config supports a
   `testIgnore` or a tag-based mechanism that excludes the test from the run; the test file
   itself carries the annotation. The annotation includes: the test id, the date the
   quarantine started, the owner, the observed failure mode, and the ticket tracking the
   resolution.
4. **Cap the number of quarantined tests.** A quarantine that grows without bound is a
   backlog of tests nobody owns. Cap the count per owner or per team, and review the cap at
   every release. Tests in quarantine past their deadline are escalated.
5. **Run quarantined tests separately, not at all.** Quarantine should not mean "never run";
   a test in quarantine still runs against `main` nightly, on a schedule, or against the
   merge queue — its result is logged but does not block. This is the only way to ensure a
  real regression inside a quarantined test is surfaced.
6. **Use flake detection tooling.** Tools that rerun failed tests in isolation (for example
   the `flake` reporter in Playwright, or a CI step that re-runs only the failed cases)
   produce a structured flake signal. Without such tooling, "flake" is a vibe; with it,
   "flake" is a counted event with a stable definition.
7. **Track flake rate, not just count.** A flake rate that trends upward across releases
   signals that the suite is degrading. Track flakes per thousand runs, per test, and per
   release. A spike that crosses the agreed threshold triggers a dedicated reduction pass
   rather than a "we'll get to it" note.
8. **Set a deadline, not an open-ended quarantine.** Quarantine without a deadline is the
   same as deletion in practice; the deadline forces the resolution into the team's normal
   cadence. A typical deadline is one release cycle; tests that exceed it are escalated.
9. **Prefer fixing over retrying.** A test that needs three retries to pass is a test with
   a stability problem. The fix is usually one of: explicit waits on stable conditions,
   isolation of shared state, removal of timing dependencies, or hardening of selectors.
   Retries mask the symptom and shift the cost onto every future CI run.

A representative Playwright configuration:

```ts
// playwright.config.ts
export default defineConfig({
  reporter: [
    ['list'],
    ['flake'] // produces a flake report alongside the standard report
  ],
  // ...
});
```

A quarantined test annotation in the file itself:

```ts
test('checkout redirects on payment failure', async ({ page }) => {
  test.fixme(true, /* metadata: owner, ticket, observed failure */);
  // body retained; the test does not run in blocking mode but runs in nightly mode
});
```

## Controls

- A quarantine list maintained in the repository (or in the test framework's annotation
  system) with owner, deadline, and ticket for each entry.
- A flake rate metric tracked in CI dashboards with an agreed alert threshold.
- A nightly run of quarantined tests whose results are visible to the same dashboards as
  the blocking suite.
- An owner assigned to every quarantined test; tests without owners are escalated.
- A deadline policy enforced by the test framework or a CI gate that fails the build when a
  test has been in quarantine past the agreed window.

## Validation evidence

- A real regression introduced into a test under quarantine is detected by the nightly run,
  with the result logged in the dashboard. The blocking suite is unaffected; the team's
  awareness of the regression is unaffected.
- A flake rate increase from 1% to 5% across two releases triggers the agreed alert and a
  reduction pass that brings the rate back below 2%.
- The quarantine count is bounded: a release where the count exceeds the cap produces a
  visible escalation rather than a silent accumulation.
- A test exits quarantine only when its flake rate at the agreed threshold is zero over a
  representative window; the exit is recorded with the runs that demonstrate it.

## Failure modes and correction

- *Quarantine becomes permanent.* A deadline is missing or routinely extended. Tighten the
  deadline, escalate extensions, and treat the deadline as a contract.
- *Quarantine grows without bound.* Cap is missing. Add the cap and the metric that
  surfaces the breach.
- *Quarantined tests do not run at all.* The nightly schedule is missing. Add it; a test
  in quarantine is a test whose regression is invisible until the next release.
- *Every failure auto-retried.* Real failures hide behind retries. Configure retry only for
  tests that have been classified as flaky, not for the suite as a whole.
- *Flake signal lost in noise.* Without a flake reporter, "flake" is anecdotal. Wire the
  reporter; review its output weekly.
- *Test deleted on first flake.* The signal is lost; the next person who adds a similar
  test has no history. Quarantine, never delete on first flake.

## Limitations

- A flake is, by definition, a test whose pass/fail is uncertain. The classification is
  itself subject to noise; a flaky test reported as flaky ten times in a row is real
  instability, not flakiness. Use the rate, not the label.
- Quarantine does not fix the flake; it defers it. The cost of an active quarantine is the
  engineering time spent fixing the underlying defect, which can exceed the cost of the
  flake itself.
- Not every flake is fixable. Tests that exercise real third-party services in real
  conditions have a non-zero flake rate that no engineering effort will eliminate; the
  policy must accept some irreducible flake.
- Quarantine policies that gate purely on count can incentivise the wrong behaviour — teams
  may merge flaky tests into fewer files, or merge similar tests, to reduce the count.
  Track distinct flake signatures, not just count.
- A policy that runs quarantined tests nightly assumes the nightly run is itself reliable.
  If the nightly environment is flaky, the signal from the nightly run is noise, and the
  quarantine cannot be cleared on its evidence.

## Canonical sources

- Google Testing Blog, *Flaky Tests at Google and How We Mitigate Them* (industry-scale
  practice for flake detection and quarantine):
  https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html
- Playwright, *Best practices* (recommended patterns for stable selectors, waits, and
  flake-resistant test design): https://playwright.dev/docs/best-practices
- Cloudflare, *Testing on Cloudflare Workers* (E2E patterns and CI guidance for environments
  that commonly host flaky network surfaces):
  https://developers.cloudflare.com/workers/testing/
