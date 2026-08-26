# wip-limits-in-practice

**Issue:** The team of eight has twenty-three items "In Progress" on the board. Every developer context-switches between a feature, two bug fixes, and a review they promised three days ago. Nothing finishes: work ages, merges conflict, and the sprint ends with fifteen items 90% done instead of eight shipped. Velocity looks stable but cycle time has tripled, and the standup is a recitation of partial progress. The team has heard "we should limit WIP" but treats it as a Scrum ceremony detail rather than an engineering lever with concrete mechanics.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why WIP limits work (the mechanics)

1. **Context switching is the tax being removed.** Human task-switching costs are well documented: attention residue means each additional concurrent task slows all of them. A WIP limit is a budget on that tax.
2. **Little's Law makes cycle time predictable.** Cycle time equals WIP divided by throughput. You cannot control throughput much day-to-day, but you can control WIP — cutting it is the only reliable lever for shorter, more predictable lead times.
3. **Limits expose bottlenecks instead of hiding them.** When the "In Review" column is capped at 3 and fills up, the blocked column is a standing signal that review capacity — not coding — is the constraint. Without a limit, the work just silently piles up there.
4. **Finishing beats starting.** A hard cap forces the question "what can I help finish?" instead of "what can I start next?", which converts idle capacity into flow instead of more partial work.
5. **The 2023+ Kanban Guide nuance.** The guide softened WIP limits from a strict requirement to "explicitly limiting WIP is often a good idea" — not because limits stopped working, but because a team that truly manages flow self-corrects without a number. Treat the limit as training wheels that make flow visible, not as the goal itself.

## Setting initial limits (first month)

1. **Start at team size minus one or two for the whole "In Progress" band.** A common opener for a team of 6 is a total WIP cap of 4-5 across dev+review columns. It will feel too low; that is the point.
2. **Cap the constraint column tightest.** If review is the known bottleneck, give it a limit of 1-2 so piling is impossible and the pain is immediate and visible.
3. **Limit columns, not just people.** Column limits surface system bottlenecks; personal limits ("I only take 2 items") are a good individual habit but hide systemic constraints from the board.
4. **Do not average.** Setting the limit at current average WIP (e.g. 15) changes nothing. Set it below the pain threshold and let the team negotiate upward only with evidence.
5. **Pair the limit with a pull rule.** Define what happens when a column is full: help finish something in it, or swarm the blocker. A limit with no agreed response just produces guilt.

## Running the practice (steady state)

1. **Empty-column rule.** When a column hits zero and upstream has work, someone pulls immediately — a starved constraint is as wasteful as a jammed one.
2. **Blocked items still count against the limit.** This is the unpopular rule that makes limits real: if a stuck PR occupies a review slot for four days, the team feels the pressure to unblock or kill it rather than route around it.
3. **Review before new work.** Adopt an explicit working agreement that an open review outranks starting a new item. This single rule fixes most "90% done" sprint endings.
4. **Adjust quarterly, not weekly.** Tune limits using flow data (cycle time percentiles, throughput) at a regular cadence. Twitching the numbers every standup destroys the signal.
5. **Track flow efficiency.** Measure touch time vs wait time on a few items. Teams are routinely shocked that items spend 80-90% of their life waiting; the WIP limit is what attacks that wait.

## Where WIP limits apply beyond the board

1. **PR-level WIP.** A per-author cap on open PRs (e.g. 2) prevents the "I opened 6 PRs and review all of them slowly" failure mode that starves reviewers.
2. **WIP limits on epics/initiatives.** Cap concurrent projects at the portfolio level — an org running 12 strategic initiatives with 6 teams has a WIP problem no team-level board can fix.
3. **Merge queue as automated WIP.** A merge queue serializes the final integration step; treat its depth as a WIP limit on "landing" and size it to CI capacity.
4. **On-call and interrupt lanes.** Reserve explicit WIP capacity (e.g. 1 slot per rotation) for interrupts instead of letting them blow through the limit and invalidate the data.

## Failure modes

1. **Limit theater.** The board shows limits but everyone routes around them via "expedite" flags or untracked branches. If expedite exceeds ~10% of items, the real process is unlimited.
2. **Limits set by the manager.** Imposed numbers get gamed; limits the team set in a flow review get defended. Facilitate, do not decree.
3. **Idleness panic.** The first weeks of a real cap produce visible idle time while waiting on the constraint. Teams abort the practice right before the flow improves. Pre-commit to 4-6 weeks before judging.
4. **Limiting coding but not review.** Capping "In Dev" while leaving review unlimited just moves the pile one column right — the tell is aging PRs with no capacity response.
5. **Confusing WIP limits with velocity targets.** Limits manage flow and predictability, not output. If leadership repurposes the limit as a quota, teams will inflate item counts and the metric dies.

## Related
- `pr-review-process-2026.md` (review capacity is usually the exposed constraint)
- `github-merge-queue.md` (serialized landing as integration WIP)
- `developer-productivity-metrics.md`, `space-framework-developer-experience.md`
- `working-agreement-template.md`
