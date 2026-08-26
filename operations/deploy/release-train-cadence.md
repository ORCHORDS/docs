# release-train-cadence

**Issue:** example project currently releases "when it's ready," which in practice means three releases land in a panic before a customer demo and then nothing ships for five weeks. Features half-done block the release for everyone else, release notes are reconstructed from memory, and every deploy is a novel event with novel failures. The team is considering a fixed release train — a scheduled, cadence-driven release — but has no written policy on cadence choice, boarding rules, or what happens when a change is not ready at departure time.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What a Release Train Is

1. **Time-based, not scope-based.** A release train departs on a fixed schedule — weekly, biweekly, monthly — carrying whatever changes are merged and green at departure. The date is fixed; the scope is variable. This is the inverse of scope-fixed, date-flexible project releases.
2. **The train is a batching mechanism.** It converts an unpredictable stream of deploys into a predictable rhythm: shared stabilisation windows, coordinated release notes, one rehearsal of the release process per cycle instead of per change.
3. **Trains sit between two extremes.** Continuous deployment ships every merge on demand (fastest feedback, requires strong automated gates — see `trunk-based-development.md`); milestone releases ship quarterly against committed scope. Trains are the middle ground for teams that need coordination but not heavy planning.
4. **It is a policy, not a tool.** SAFe's Agile Release Train formalizes the same idea with 8–12 week Program Increments; a small product team gets most of the benefit from a biweekly tag-and-ship with a one-day stabilization window, without the ceremony.

## Choosing the Cadence

1. **Match cadence to test-cycle length.** The interval must comfortably exceed the time to run the full verification suite (automated regression, staged rollout observation window). If full verification takes 3 days, a weekly train is already tight; a daily train is theater.
2. **Shorter trains lower risk per departure.** Smaller batch per release means fewer changes to bisect when something breaks and less pressure to hold features back — the failure modes of long trains are exactly the batching risks of big-bang releases.
3. **Longer trains buy coordination.** Cross-team dependencies (mobile + backend + docs translations) synchronize more cheaply on a monthly train than on weekly ones; if three teams must move together, one shared train beats three desynchronized rhythms.
4. **Pick a boring, recurring slot.** Second Tuesday, 10:00, same every cycle. Avoid days adjacent to known freeze windows (see `deployment-freeze-policy.md`) and avoid Friday departures unless the on-call rotation is explicitly staffed for it.
5. **Revisit the cadence quarterly.** If trains routinely depart nearly empty or routinely overflow, the interval is wrong; a train that always carries 40 PRs is a big-bang release wearing a schedule.

## Boarding Rules

1. **Merged and green by cut-off boards the train.** The boarding condition is objective: merged to the release branch/main, all required checks green, and the change flagged for release (release-branch flow) or simply present (trunk flow). Anything else waits for the next train — no exceptions granted by seniority.
2. **Incomplete features ride behind flags.** A half-finished feature merges dark (flag off) and boards any train; the flag flip becomes a later, independently revertable change. This is how trains stay compatible with ongoing work — see `feature-flag-deploy-coupling.md`.
3. **The train does not slow down for stragglers.** If a change misses the cut-off, it waits for the next departure. Holding the train for one feature re-creates the scope-blocked release the train was adopted to kill.
4. **Hard-exclusion list applies even at cut-off.** Red builds, failing migration gates (see `database-migration-deploy-strategy.md`), and changes without required docs/owners do not board, regardless of how close they were.
5. **Cut-off is announced in the release issue.** Open a recurring "Release 2026.08.18" issue at the start of each cycle listing cut-off time, boarding checklist, and current manifest; transparency prevents last-minute arguments about what made it.

## Running the Train

1. **Stabilisation window before departure.** Reserve the last 10–20 percent of the cycle for the release candidate: freeze new merges to the release branch, run the full regression suite, execute deploy drills against staging. Bugs found here either fix fast or de-board (revert) — the train still departs.
2. **One rehearsed departure procedure.** Same steps every cycle: tag, changelog generation (see `changelog-generation.md`), deploy to staging, smoke tests, staged production rollout, post-deploy verification, release-notes publication. Novelty in the release process is where releases fail.
3. **Notes are generated, not written.** Conventional commits plus automation produce the draft; a human edits for tone for 15 minutes. Writing release notes by hand each cycle is the first thing teams quietly stop doing.
4. **Announce and annotate.** Post departure to the team channel and push a deploy marker to dashboards so any metric shift in the following 48 hours is attributable to the release.

## Missing the Train, Metrics, and Failure Modes

1. **Deferral is normal, not failure.** The train's promise is predictability, not that every change ships on first attempt; the health metric is time-from-merge-to-release staying under one cycle plus change-failure-rate (see `change-failure-rate.md`), not 100 percent boarding.
2. **Track the boring numbers per cycle.** Changes boarded, changes de-boarded and why, departure delay (should trend to zero), rollback rate, and lead time for a hypothetical urgent fix. If urgent fixes cannot jump the train, people will route around it — give hotfixes a documented exception lane per `hotfix-branching-deployment-discipline.md`.
3. **Failure mode: train-as-theater.** If deploys still happen off-schedule "just this once" weekly, the train is decorative; either fix what makes scheduled departures untrustworthy or admit the team wants continuous deployment and adopt it properly.
4. **Failure mode: release-branch drift.** Release-flow trains rot when fixes land on the release branch but nobody merges back to main (or vice versa); enforce merge-back in the same cycle, or prefer trunk-based trains with flags to eliminate the second branch entirely.
5. **Failure mode: cadence gravity.** Teams start treating the train as a deadline and inflate scope to "make this cycle," re-importing big-bang risk in smaller boxes. The cut-off rule is the antidote: scope never negotiates with the schedule.
