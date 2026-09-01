# Developer Onboarding First Commit Cadence

## Scope

This article covers the onboarding practice of measuring and driving new-developer time-to-first-commit: why the metric is worth tracking, what a good target looks like, what the first-commit pathway must contain, and how to read the metric without gaming it. It applies to engineering organizations of any size that hire or internally transfer developers. It does not cover the full onboarding curriculum, buddy program design, or performance evaluation of new hires.

## Workflow or implementation guidance

Time-to-first-merged-commit is the single most informative onboarding metric available, because it is a lagging composite of everything that can go wrong: environment setup that takes three days, access requests that wait a week for approval, a repository nobody can build locally, a review process nobody explained, and a first task chosen so large the new hire cannot finish it. The metric does not diagnose which of these failed — that is the follow-up work — but it detects that something did, within the first two weeks, when fixing it still matters.

Define the clock precisely, or the number becomes noise. Start: the new developer's first working day. Stop: the moment a commit authored by them is merged to the default branch of a production repository. Exclude pre-employment paperwork and machine procurement if those precede day one, but include everything the developer experiences from day one onward — waiting for credentials is onboarding time, not an asterisk. Count internal transfers with the same clock; they are often slower than external hires because everyone assumes they already have access.

Targets by context, because a single number punishes legitimate differences: for a small team on a single service with paved-path tooling, two business days is achievable and appropriate. For a large organization with compliance-driven access provisioning, five business days is honest. What is not acceptable anywhere is a two-week median with a six-week tail, and the tail matters more than the median — a median of three days with a 90th percentile of thirty days describes an organization where onboarding works if you are lucky.

The pathway itself is a designed sequence, not a hope. It has five stations, and the onboarding program owns each one.

**Station 1 — Working environment, day one.** The repository builds and its test suite passes on a fresh clone with documented, scripted setup — a container, a devcontainer, or a single bootstrap command. Every hour the environment does not work is an hour charged to the platform team, not the new hire. The setup script is tested the way other software is tested: by running it from clean state periodically.

**Station 2 — Access, day one.** Repository read, CI visibility, the tracker, chat channels, and the deployment dashboard, all provisioned before or on arrival through group membership rather than individual grants. Access tickets are the most common single cause of a blown clock, and they are a provisioning-system problem, not a new-hire patience problem.

**Station 3 — A scoped first task, by day two.** The first task is a good-first-issue-grade change: real, merged to production code, completable in a day or two by someone who does not yet know the codebase. The canonical shapes: a small bug fix with a known cause, a missing test for existing behavior, a small documentation correction, or a log-message improvement. The task exists precisely to walk the new hire through the entire pipeline — branch, change, PR, review, CI, merge, deploy — with low stakes.

**Station 4 — The pipeline walkthrough.** The first PR is where process knowledge transfers: branch naming, commit conventions, PR template, review expectations, and what happens after merge. The assigned reviewer reviews the first PR as teaching, not gating — detailed, explanatory, and fast, same-day turnaround. A first PR sitting unreviewed for three days teaches the new hire exactly the wrong lesson about how the team treats each other's work.

**Station 5 — The cadence ramp.** After the first merge, the target is a commit every one to two days through the first month, on progressively larger tasks. This cadence is not a quota; it is a proxy for whether friction keeps getting removed. If commit frequency collapses in week three, the cause is usually task sizing or review latency, both fixable.

Read the metric as a distribution with a median, a 90th percentile, and a cohort count. Read it alongside one companion number — new-hire-reported setup friction from a short survey at day five — because time-to-first-commit measures the clock, and the survey catches problems the developer silently worked around. And always interview the tail: the person whose first commit took five weeks will name the specific broken station, and that name is worth more than the aggregate.

Anti-gaming note: the metric is about the path, not the person. A team that achieves day-one commits by handing the new hire a trivial typo fix to merge and calling it onboarding has optimized the number and lost the signal. The first commit must traverse the real pipeline, because the pipeline walkthrough is the point.

## Controls

- A precisely defined clock: first working day to first commit merged to a production repository's default branch.
- Context-based targets (two business days small team, five days compliance-heavy org), tracked as median plus 90th percentile plus cohort size.
- Five owned stations: scripted environment, day-one access via group provisioning, scoped first task in the backlog, teaching-quality first review with same-day turnaround, cadence ramp through month one.
- Good-first-issue backlog maintained with at least two tasks open at all times.
- Day-five friction survey paired with the metric.
- Tail interviews for every cohort member beyond the 90th percentile.

## Validation evidence

Verification for this practice combines measurement with spot-checks of the stations:

- Compute the metric per cohort from the version-control history: first commit authored by each new hire merged to the default branch, timestamped against start date. Confirm the distribution is reported with median and 90th percentile, not a mean.
- Test the environment script from a clean machine quarterly; the elapsed time to a passing test suite is the station's true service level.
- Run an access audit at each cohort start: confirm repository, CI, tracker, and chat access were live on day one, and measure any provisioning lag.
- Audit the first task assigned to each new hire against the scoping criteria — completable in one to two days, merged to production, traversing the full pipeline. Trivial-fix-only first tasks are flagged as metric gaming.
- Sample first PRs for review turnaround time; first-review latency should be materially better than the team's median review latency.
- Correlate the day-five survey scores with the measured clock each cohort; divergence between them indicates silent workarounds and triggers interviews.

## Failure modes and correction

- **Metric worship.** Day-one commits via trivial merges that teach nothing. Correction: the first task must traverse the real pipeline; audits flag checkbox onboarding.
- **Environment decay.** The setup script rots and each cohort's first week becomes debugging YAML. Correction: the script is tested from clean state on a schedule; breakage is a platform-team bug.
- **Access lottery.** Some hires get day-one access and some wait a week depending on who filed what. Correction: group-based provisioning triggered by the hiring record, not individual tickets.
- **Missing first task.** The new hire arrives to an empty good-first-issue backlog and gets "look around the codebase" for a week. Correction: maintaining two open first tasks is an owned responsibility with a named owner.
- **First-review neglect.** The first PR waits behind routine reviews. Correction: first PRs are marked and prioritized; their latency is measured separately.
- **Median blindness.** A healthy median hides a terrible tail. Correction: the 90th percentile is part of the reported metric, and every tail case gets an interview.

## Limitations

Time-to-first-commit measures pipeline friction, not learning, contribution quality, or long-term retention — a fast first commit predicts nothing about the sixth month, and treating it as a performance indicator of the new hire rather than the system corrupts the measure immediately. The metric assumes a traditional PR workflow; teams where the first contribution is a design document or an infrastructure change need a different first-artifact definition. Context-based targets are calibrated judgment, not benchmarks, and organizations comparing themselves across contexts will draw wrong conclusions. The cadence ramp can misread deliberate ramp-up patterns — a new senior engineer spending week two reading code before a large change is not a failure, and quota-thinking will pressure exactly the wrong behavior. Survey data depends on psychological safety; new hires who report no friction because reporting is risky make the paired metric lie.

## Canonical sources

- DORA — Research on developer productivity and delivery performance: https://dora.dev/research/
- DORA — The four keys metrics (lead time and deployment frequency context): https://dora.dev/guides/dora-metrics-four-keys/
- GitHub Docs — Creating and deleting branches within your repository (first-contribution pathway): https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-and-deleting-branches-within-your-repository
- Atlassian Git tutorials — Syncing (first exposure to remote workflow): https://www.atlassian.com/git/tutorials/syncing
