# onboarding-buddy-system

**Issue:** A new engineer's first weeks set the trajectory of their first two years, yet most teams delegate onboarding to a wiki page and the manager's spare moments. The new hire's small questions ("which channel do I ask in?", "how do I run the tests?") queue behind a busy manager, so they either stall or guess wrong. A buddy system fixes the channel, not just the content: it pairs every new hire with an experienced peer, deliberately separate from the manager, whose job is day-to-day question-answering and cultural translation. The measurable impact is large — 2025-2026 onboarding research reports that assigning a buddy makes onboarding roughly 3.5 times more effective, with new hires reporting around 23 percent higher onboarding satisfaction — and the practice is now standard guidance from engineering onboarding guides (Cortex, Enboarder) through to Meta's internal playbook described by Ryan Peterman.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Role definition and boundaries

1. **The buddy is a peer, not the manager and not the mentor-of-record.** The buddy handles the small, constant, low-stakes questions — tooling, norms, where things live — so the manager can focus on scope, expectations, and growth. Formal technical mentorship is a separate, later relationship with different matching.
2. **Buddy is a time-boxed tour of duty.** The commitment runs roughly the first 60-90 days with a decreasing cadence: near-daily in week one, a few times a week by month two, then handoff to normal team channels. Open-ended buddy duty burns out the kindest engineers.
3. **Buddies answer "how," managers answer "what and why."** Write the boundary down. When a question becomes a performance, scope, or interpersonal issue, the buddy's job is to route it to the manager, not to absorb it.
4. **No evaluation role.** The buddy does not report on the new hire's progress as a judge. The moment the buddy becomes an assessor, psychological safety — the entire value of the relationship — evaporates.

## Selecting and preparing buddies

1. **Volunteers first, then arm them.** Buddy work is a service role; conscripts do the minimum. Ask for volunteers who remember being new, then give them a checklist, a short guide on what good looks like, and visibility that the role counts in performance conversations.
2. **Pick engineers one to three years ahead of the new hire.** They remember the gotchas recent grads actually hit and have current muscle memory for the toolchain. The most senior engineer is often the worst buddy for a new grad.
3. **Never onboard a buddy and a new hire simultaneously on the same knowledge.** The buddy must have shipped at least one meaningful change in the repo the new hire will work in.
4. **Prepare before day one.** Accounts, access, hardware, and repo permissions must exist before the new hire arrives, so the buddy spends the first day on people and code, not IT tickets — day-one access failures consume the buddy's goodwill immediately.

## The first 30-60-90 days

1. **Week one: presence over curriculum.** The buddy's job is a daily check-in, lunch company, and getting the new hire's first commit merged — however trivial. An early win in week one is the strongest known predictor of fast ramp.
2. **Introduce the question pathways.** Explicitly teach where to ask what: which channel for quick help, forum for async questions, ticket for tracking, meeting for design. New hires who learn the pathways early stop depending on the buddy naturally.
3. **Curate good first issues.** The buddy works with the manager to line up a graduated ladder of starter tasks that touch the deploy pipeline, the review process, and one real bug — small PRs that traverse the whole system quickly.
4. **Month two: shadow and be shadowed.** The new hire shadows the buddy in a code review or incident drill; later the buddy shadows the new hire leading a small task. Reversing the flow builds confidence and surfaces gaps the buddy assumed were obvious.
5. **Month three: taper and graduate.** Check-ins drop to weekly, then the relationship formally closes with a short handoff note to the manager covering anything still unclear. Ambiguous endless buddy relationships help nobody.

## Measuring success

1. **Time to first merged PR, tracked as a team metric.** A healthy buddy system reliably gets new hires to a merged change in the first week; a drift toward two weeks is a leading indicator of onboarding rot.
2. **30-60-90 retros with the new hire.** Ask what was confusing, what the buddy covered well, and what to fix for the next hire — and feed it back into the checklist. The onboarding doc should improve with every hire.
3. **Track 90-day and 12-month retention.** Retention is the slow metric that buddy programs reliably move; cohort it by whether the hire had an active buddy.
4. **Survey the buddies too.** If buddies report the role as unrecognized burden, the pipeline of future volunteers dries up, and the program quietly ends.

## Sustaining the program

1. **Maintain a standing buddy roster.** At least two trained buddies ready per expected hire, refreshed quarterly, so matching never depends on whoever happens to be free.
2. **Give the role visible credit.** Name buddy service in performance review inputs and team announcements. Uncredited infrastructure fails at the first busy quarter.
3. **Keep the onboarding checklist in version control.** The buddy curriculum, first-issue ladder, and week-one script live in the repo where any engineer can PR improvements — the doc is code, and the buddy is its runtime.
4. **Rotate deliberately.** Each engineer should buddy roughly one new hire per year at most, enough to keep the muscle fresh without making it a second job, and every buddy should have been buddied themselves.
