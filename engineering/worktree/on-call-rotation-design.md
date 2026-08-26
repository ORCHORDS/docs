# on-call-rotation-design

**Issue:** A product team stands up its first 24/7 on-call rotation and burns people out within two months. Three engineers share the pager, one of them gets every weekend page because "he knows the system best," half the pages are automated alerts nobody can act on, and escalation means "ping the tech lead on Slack and hope." Rotation design — sizing, scheduling, escalation structure, and page hygiene — was never planned; it was inherited from whatever the alerting tool defaulted to.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Rotation sizing and shift structure

1. **Six engineers minimum per rotation.** Four is the absolute floor (one-in-four weekly means three recovery weeks per on-call week); six to eight is the healthy target because it absorbs vacations, departures, and uneven page load without collapsing into back-to-back shifts.
2. **Weekly shifts for standard SaaS teams.** One week primary is long enough to build context and short enough to bound fatigue. Twelve-hour shifts suit 24/7 operations with high page volume — they minimize handoffs while keeping fatigue risk manageable.
3. **Always run primary plus secondary.** The secondary absorbs overflow when the primary is mid-incident, on a call, or simply stuck. Secondary also functions as a shadow slot for training new on-calls before they take primary.
4. **Publish schedules 4–6 weeks ahead.** People plan lives around on-call weeks; last-minute schedule churn is a top driver of resentment. The schedule lives in the paging tool, not a spreadsheet.
5. **No back-to-back shifts, ever.** Anyone who finishes an on-call week and is immediately scheduled again has been set up to fail — enforce a minimum one-week gap in the scheduling tool, not by memory.
6. **If you cannot staff a humane rotation, do not run one.** A rotation below four people should downgrade to business-hours coverage with an explicit escalation contract to a broader team, rather than slow-roasting two volunteers.

## Follow-the-sun vs follow-the-moon

1. **Follow-the-sun passes the pager with the daylight.** Each region takes on-call during its own business hours, so nobody is paged overnight. The cost is two to three ownership handoffs per day, each of which is a context-loss risk.
2. **Handoff ritual makes or breaks follow-the-sun.** Require a written handoff log (open incidents, watch items, ongoing deploys) exchanged in a structured window around shift change. Verbal-only handoffs guarantee dropped context within a month.
3. **Follow-the-moon ships the night to someone else's day.** Overnight coverage is deliberately concentrated in a region for whom those hours are daytime. It protects the primary team's sleep but creates an equity problem: one location permanently handles the ugliest hours.
4. **Rotate night-adjacent duty fairly in any moon-style model.** If one region or subgroup always absorbs night coverage, fatigue simply moved rather than disappeared — rotate who takes the night block on a multi-week cycle.
5. **Most single-timezone teams should do neither.** Without genuine geographic distribution, the honest model is a weekly rotation with a night-paging policy: only truly urgent pages at night, everything else waits for morning. Do not fake follow-the-sun with one engineer in a distant timezone.

## Escalation chain design

1. **Primary → secondary → manager/engineering director.** Each hop has an explicit paging target (a rotation, a named person, or a schedule-managed group) — never a team alias nobody watches.
2. **Escalate on timeout, not on human decision.** If the primary does not acknowledge within a fixed window (commonly 5 minutes), the pager escalates automatically. Requiring a stressed on-call to decide whether to "bother" the secondary guarantees pages sit unacknowledged.
3. **Escalate skill as well as availability.** For specialized services, the chain should reach a service expert rotation, not just a hierarchy of managers — a director woken at 3am cannot fix a Kafka rebalance loop.
4. **Business-hours and after-hours chains differ.** After-hours escalation should be shorter (fewer hops, faster paging) because there is no ambient team in Slack to absorb the question first.
5. **Test the chain quarterly.** Fire a synthetic page through the full chain in a scheduled game-day exercise; broken phone numbers, stale schedule overrides, and departed employees are found this way, not during an outage.

## Page quality rules

1. **Page only when a human must act now.** Every alert gets classified as actionable (immediate human response required), informational (context, routed to chat or a ticket), or noise (deleted). Only the first category reaches the pager — everything else is reporting.
2. **Alert on symptoms, not causes.** Page on user-visible failure (error rate, latency, availability); causes (high CPU, disk nearly full) become tickets unless they reliably predict a symptom. Symptom alerts survive refactors; cause alerts rot.
3. **Deduplicate and group.** One underlying failure often fires twenty alerts; group by service and dependency so it produces one page with context, not a pager storm that teaches people to ignore their phones.
4. **Every page links a runbook.** If the on-call's first action would be "figure out what this alert even is," it is not actionable yet. An alert without a linked runbook and a first step does not qualify for paging.
5. **Audit paging rules monthly.** Review false-positive pages and repeated non-actionable pages, and delete or demote offenders. GitLab's on-call-noise reduction and the incident.io 2026 guide both converge on the same discipline: the ratio of actionable pages to total alerts is the health metric.
6. **Flappy alerts are disabled same-week.** An alert that fires and self-resolves repeatedly erodes trust in every other page; disable it, fix the threshold, then re-enable.

## Burnout signals and countermeasures

1. **Track pages per shift per person.** A sustainable week is roughly two pages or fewer; sustained weeks of five-plus pages, or any single night with more than three pages, predict attrition. Uneven distribution (one person paging far more than peers) is the earliest warning sign.
2. **Measure acknowledgment and resolution times, not heroism.** Long acknowledgment gaps indicate fear or exhaustion, not dedication; use them to start a conversation, not to rank engineers.
3. **Compensate the time.** Whatever the model — on-call pay, time-off-in-lieu, or a lighter sprint load during on-call weeks — unpaid, unacknowledged disruption is the fastest route to "I'm done taking the pager."
4. **Run an on-call fatigue pulse.** A two-question survey after each rotation cycle (how was your week, what paged you that shouldn't have) feeds the page-quality audit and surfaces problems months before resignations do.
5. **Watch the DORA trap.** Elite delivery metrics achieved by sacrificing on-call health and working nights look great right up until 40% attrition — review reliability metrics and human sustainability together, never separately.

## Source URLs (verified 2026-08-15)

- https://incident.io/blog/on-call-best-practices-guide-2026
- https://oneuptime.com/blog/post/2026-02-02-on-call-rotations/view
- https://firehydrant.com/blog/best-practices-for-creating-on-call-rotations-and-schedules/
- https://about.gitlab.com/blog/reducing-pager-fatigue-and-improving-on-call-life/
- https://en.wikipedia.org/wiki/Follow-the-sun
- https://rootly.com/on-call-software/schedules-and-rotations
