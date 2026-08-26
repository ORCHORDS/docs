# good-first-issue-maintenance

**Issue:** The repo advertises 14 `good first issue` tasks to attract contributors, but the list is fiction: three were silently fixed months ago, two depend on an API that no longer exists, four have an unmerged drive-by PR rotting on them, and the rest lack enough context for a newcomer to start without interviewing a maintainer. New contributors burn a weekend getting a dev environment up only to find their chosen issue is unbuildable, then leave a "is this still relevant?" comment and never return — and by 2025-2026 community discussions (notably in Scientific Python circles) had soured on the label entirely, calling it "highly problematic for years" because unmaintained good-first-issues generate spam for maintainers and burned goodwill for newcomers. The label is a promise of a working on-ramp; keeping that promise is an ongoing maintenance obligation, not a one-time tagging act.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Qualification criteria before tagging

1. **A maintainer has reproduced the fix path.** Someone with commit access has mentally (or actually) walked the change and can name the files involved — "probably easy" is not a qualification, it is a guess.
2. **The task is scoped to one PR.** If the fix realistically touches multiple modules or needs a design decision, it is a `help wanted` task, not a first issue; scope creep is the newcomer's worst first experience.
3. **The issue body is self-sufficient.** Repro steps, expected behavior, file pointers, and acceptance criteria are written down; a task that requires tribal knowledge filters for insiders, not newcomers.
4. **The environment builds today.** The contributing quickstart must work from a clean clone on the supported platforms before any issue can honestly be labeled newcomer-ready.
5. **It teaches one thing.** The best first issues introduce exactly one subsystem or convention (adding a config flag, one endpoint, one test fixture) so completion produces learning, not bewilderment.

## Freshness verification cadence

1. **Audit the label on a fixed cadence.** A monthly pass over every open `good first issue` checks: still reproducible, still relevant, comments answered, no conflicting PR attached.
2. **Expire the tag on merge or drift.** When an unrelated refactor changes the affected code, re-verify the issue body still names real files — stale pointers make the issue a trap even when the bug is real.
3. **Make the stale policy label-aware.** Stale automation must exempt claimed first issues but aggressively age unclaimed ones, since an untouched good-first-issue past 60 days is usually fiction.
4. **Cap the open count.** A working set of 3-6 verified tasks beats a museum of 30 unvetted ones; a small queue that actually converts is the credibility play.
5. **Kill "already fixed" on sight.** Any issue confirmed fixed elsewhere closes immediately with a thank-you to whoever reported the residual, because every zombie in the list taxes every future audit and every newcomer search.

## Handling drive-by contributions

1. **Expect and triage the flood.** Hacktoberfest-season and tutorial-driven PRs arrive half-broken; treat them as the cost of the label and budget review time for them rather than resenting them.
2. **One claim per issue, timeboxed.** Ask newcomers to comment "taking this" and give a soft deadline (e.g. two weeks with a check-in); after that the issue reopens for others without drama.
3. **Review first contributions as teaching.** The first review a contributor receives sets the project's reputation — point at the contributing guide, explain the "why" behind requests, and never land a drive-by-close without a pointer forward.
4. **Do not let partial PRs squat.** An abandoned half-merged PR on a good first issue blocks the next contributor; close it with an explanation and a note that the approach can be reused, then re-open the field.
5. **Promote success.** A completed first issue should graduate its author toward a `help wanted` task or docs improvement — the funnel only pays off if there is a second step.

## Onboarding experience requirements

1. **The label links to a quickstart.** Every good-first-issue body carries a line pointing at the setup doc and the community channel, because environment setup — not the task — is where most newcomers die.
2. **A named buddy.** Assign one maintainer as reviewer-of-record for each tagged issue so questions have an addressee instead of broadcasting into the void.
3. **Seed test-first tasks.** Issues of the form "add a test reproducing X" or "fix this failing assertion" are ideal first issues: verifiable, low-risk, and genuinely useful even before the fix lands.
4. **Keep CONTRIBUTING current.** The quickstart is verified in the monthly audit alongside the issues, since a broken setup doc invalidates every tagged task at once.
5. **Respond within a stated SLA.** Publish a response expectation (e.g. first reply within a week); unresponsive maintainers on tagged issues is the top reason newcomers call a repo "dead" regardless of activity elsewhere.

## Metrics that prove the funnel works

1. **Conversion rate.** Tagged issues → opened PRs → merged PRs; a tag that produces opens but never merges is decorative.
2. **Time-to-first-response.** Median hours from newcomer comment to maintainer reply is the single best predictor of whether a contribution survives.
3. **Return rate.** Share of first-time contributors who file a second PR — the real goal of the label is alumni, not one-offs.
4. **Audit debt counter.** Days since the last full good-first-issue audit, kept visible; when it grows past the cadence, the label's promise is technically void.
