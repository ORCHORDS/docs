# code-review-sla-sizing

**Issue:** Pull requests that sit unreviewed for days are one of the largest hidden taxes on engineering throughput. While a PR waits, the author context-switches to new work, merge conflicts accumulate, and the queue of open reviews grows until nobody can find focused review time at all. Teams often respond with a vague aspiration ("be responsive") rather than a concrete, sized service-level agreement, which makes the promise unenforceable and unmeasurable. An SLA that is too aggressive for the team's real review capacity breeds burnout and rubber-stamping; one that is too loose delivers no improvement. The problem is therefore not whether to set a code review SLA but how to size one honestly against team size, time zones, reviewer pool, and PR volume, and how to instrument it so the agreement survives contact with reality.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Sizing the SLA

1. **Anchor to one business day, aim for hours.** Google's engineering practices guidance treats one business day as the maximum acceptable time to respond to a review request, with a response within hours as the target and immediate turnaround for urgent or tiny changes. Anything longer than a day and the author has already lost the mental model of the change.
2. **Tier the commitment by PR size.** A single-digit-line change should get first review inside four hours; a medium PR inside one business day; an explicitly labeled large PR may carry a two-day expectation because the reviewer must schedule a block of focus time. One flat SLA for all PRs is the most common sizing mistake.
3. **Budget reviewer capacity explicitly.** If a team of six opens three PRs per day and each review costs twenty to forty minutes, that is one to two hours of daily review load per engineer. Publish this number. If the math does not fit inside the team's day, the fix is fewer or smaller PRs, not a looser SLA.
4. **Cap review size at roughly four hundred lines.** Research popularized by SmartBear found review effectiveness drops sharply beyond 200-400 changed lines. Enforcing a soft size cap through PR templates and automation keeps every review inside the fifteen-to-sixty-minute window the SLA assumes.
5. **Distinguish first response from full approval.** The SLA should promise a first substantive response (comments, questions, or approval) within the window, not final approval. Requiring final approval on a fixed clock pushes reviewers to approve prematurely.

## Making it enforceable

1. **Measure first response time and time-to-merge separately.** First response exposes reviewer responsiveness; time-to-merge exposes the whole loop including author rework. Dashboards that blend the two hide which side of the exchange is slow. Benchmarks from review-analytics vendors treat sub-four-hour first response as top-quartile and sub-24-hour merge as acceptable.
2. **Schedule dedicated review slots.** Teams that block two fixed review windows per day (for example, after standup and mid-afternoon) hit SLAs without feeling interrupted, because reviews batch naturally. Ad-hoc reviewing between tasks is the pattern most correlated with missed targets.
3. **Automate everything that is not judgment.** Formatting, linting, type checks, and tests must pass before a human is asked to look. Every mechanical comment a reviewer leaves is a signal the CI gate was under-built and a tax on the SLA budget.
4. **Route by CODEOWNERS, not by ping.** Automatic reviewer assignment through ownership rules removes the "who should look at this" delay that often consumes more wall-clock time than the review itself. Review rotation spreads load evenly instead of concentrating it on the one person who never says no.
5. **Publish the SLA in the PR template.** Stating the expected response window in the PR description sets author expectations and gives reviewers a shared, visible commitment rather than a private guilt mechanism.

## Adapting to team shape

1. **Handle time zones with follow-the-sun honesty.** For a team split across Europe and the Americas, "one business day" must be defined in the receiver's business day, not the author's. A PR opened at 17:00 CET should not be flagged as breaching SLA at 09:00 CET the next morning before the Americas team has even started.
2. **Give senior reviewers a lower concurrent load.** Architects and staff engineers attract the hardest reviews. Cap their simultaneous open-review count (two or three) and route routine reviews elsewhere, or the SLA will be breached specifically on the riskiest changes.
3. **Escalate stalled reviews rather than silently waiting.** After the SLA window passes, the author should have a defined escalation path: a polite channel nudge at one day over, then a manager or lead flag at two. Without escalation, an SLA is only a statistic.
4. **Exempt with labels, not with silence.** Draft PRs, spike branches, and docs-only changes should be explicitly excluded from the clock via labels so the metric stays clean and the exceptions stay visible.
5. **Revisit the sizing quarterly.** Team size, service ownership, and PR volume drift. A quarterly review of first-response percentiles against the stated SLA tells you whether to tighten the target, invest in automation, or split the reviewer pool.
