# sprint-commitment-realism

**Issue:** Teams chronically overcommit. Sprint after sprint, planning fills every point of nominal capacity, unplanned work (production bugs, support escalations, review debt) arrives as it always does, and 30-40 percent of the sprint rolls over — followed by the retro where everyone agrees to "commit to less" and the next planning fills every point again. The costs compound: forecasts to stakeholders become fiction, carryover items lose context and get re-explained, and engineers learn that commitments are decorative, which corrodes the one function planning actually has — creating a reliable prediction. Commitment realism is the discipline of sizing the sprint against demonstrated throughput and measured interrupt load rather than against hope. This article covers the evidence to plan from, how to structure the commitment, and how to correct the habit once it has set in.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Planning from evidence instead of aspiration

1. **Commit from historical throughput, not next-sprint ambition.** The core planning number is what the team actually completed over the last several sprints, not what it believes it could do at full stretch. Velocity guidance is unambiguous on this point: use the average (or better, a range) of completed work, because completed is the only outcome with evidence behind it.
2. **Distinguish velocity from capacity.** Velocity is demonstrated throughput; capacity is theoretical availability. Engineering-effectiveness analysis (DX and similar) flags the classic trap from both directions: planning purely by capacity overloads a team mid-change, while forecasting purely by velocity ignores planned absences and hires. Realistic commitment uses both — throughput as the base, capacity as the adjustment.
3. **Wait for signal before trusting the numbers.** A team needs roughly four to six sprints of history before its velocity means anything; new and re-formed teams are too variable, and guidance for onboarding teams suggests cutting initial commitments by 30-50 percent until the data stabilizes. Planning a brand-new team at full capacity is the most predictable overcommitment there is.
4. **Measure the interrupt tax and subtract it up front.** Pull the actual fraction of recent sprints spent on unplanned work — emergent bugs, support, urgent stakeholder asks — and reserve that slice explicitly. If 25 percent of the last three sprints went to interrupts, planning 100 percent committed work guarantees rollover by arithmetic, not by bad luck.

## Structuring a commitment that survives contact with the sprint

1. **Agree the sprint goal before pulling a single item.** With a goal stated first, items get selected for whether they serve it; without one, the sprint fills by size until points run out, which is how unrelated stragglers end up "committed" and rolled over forever. The goal is also what makes mid-sprint tradeoff decisions fast.
2. **Aim to fill 80-85 percent of expected capacity.** The shortfall is the shock absorber for the interrupt load you measured and the estimation error you cannot. A team that plans to exactly 100 percent has committed to zero surprises, which no sprint in history has achieved.
3. **Refine two to three sprints deep.** Planning meetings turn into estimation scrambles when candidate items are unrefined — unestimated, missing acceptance criteria, oversized — and scramble-planning is where fantasy commitments originate. Planning guidance consistently ties realistic commitments to a ready backlog: the sprint gets filled from prepared, sized items, with the deep-refinement cadence covered by the grooming discipline.
4. **Pull items in priority order and stop when full.** Not until every stakeholder request has a home in the sprint. Unpulled items stay visible in the backlog queue; pretending they fit this sprint does not make them fit, it just moves the disappointment to the demo.
5. **Write the carryover decision rule down.** When items roll over, the default disposition is decided in advance: re-pull only if still top priority, return to the backlog otherwise. Carryover by inertia — same item, fourth sprint, no re-examination — is how stale work consumes capacity invisibly.

## Correcting an overcommitment habit

1. **Track commitment-versus-completion as a team metric, blamelessly.** Plot planned against delivered for the last ten sprints. Most overcommitting teams have never seen this chart; seeing six consecutive sprints at 70 percent lands differently than another retro anecdote. Track it as a calibration measure, not a performance target — the goal is an accurate forecast, not 100 percent completion.
2. **Inspect rollover reasons and fix the biggest bucket.** Items roll for three distinct causes: underestimated effort (estimation problem), interrupts (reservation problem), or blocked dependencies (planning problem). Each has a different fix, and treating them as one undifferentiated "we committed too much" prevents any of the three fixes.
3. **Use probabilistic forecasting for dates beyond the sprint.** For release milestones, Monte Carlo-style simulation over historical throughput ("how many sprints until this scope is 85 percent likely done?") beats dividing scope by average velocity, because it answers in likelihoods and exposes risky plans as wide distributions. Deterministic date math hides the variance; simulation prices it.
4. **Let the forecast be wrong loudly.** When mid-sprint reality diverges from the plan — a task ballooned, an incident ate a week — re-forecast immediately and communicate the slip now. Teams hide divergence until the demo, stakeholders learn plans are fiction, and the trust cost exceeds the slip cost every time.

## Signals the commitment is finally realistic

1. **Completion lands in a stable band sprint over sprint.** Not 100 percent — 80-95 percent with occasional swings from genuine surprises is what calibrated looks like. Perfect delivery every sprint usually means sandbagging, which is its own forecasting failure.
2. **Carryover shrinks to items that genuinely could not finish.** No more fourth-sprint zombies; rollovers are recent, understood, and re-prioritized deliberately.
3. **Interrupts are planned, not suffered.** The reserved slice gets used roughly as sized, and when a quarter's interrupts consistently run under the reservation, the reserve shrinks and capacity genuinely grew — the metric improving for the honest reason.
