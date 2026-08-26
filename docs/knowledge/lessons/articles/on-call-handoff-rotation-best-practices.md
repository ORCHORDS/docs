# On-Call Handoff — Rotation Design and Burnout Prevention

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your on-call rotation has two people covering all services 24/7. One
engineer gets paged 15 times during a single night shift and is
exhausted the next workday. Handoff between rotations is a Slack message
saying "your turn" with no context on active incidents, pending alerts,
or known issues. When the new on-call gets paged for an ongoing issue,
they waste 30 minutes understanding context that the previous on-call
already had. Senior engineers refuse to join the rotation because it is
seen as thankless and career-damaging.

## Context

On-call rotation is the practice of assigning engineers to be available
for incident response outside business hours. In 2026, healthy on-call
programs treat on-call as a first-class engineering responsibility with
compensation, bounded scope, and systematic burnout prevention. The
industry standard is 1-week rotations with a primary and secondary
on-call, formal handoff documents, and a target of fewer than 2
actionable pages per on-call shift. Organizations like Google, Meta, and
Stripe publish on-call best practices emphasizing that sustainable
on-call is a prerequisite for reliable systems — burned-out engineers
make worse decisions during incidents.

## Rotation design

```
Primary/secondary model:
  Primary:   first responder, handles all pages
  Secondary: backup if primary doesn't respond within SLA (15 min)
  Escalation: engineering manager after 30 min

Rotation length:
  → 1 week (industry standard)
  → Handoff on a weekday (Tuesday or Wednesday)
  → Never hand off on Friday (weekend context loss)
  → Never hand off on Monday (weekend carryover)

Team size:
  → Minimum 4-5 engineers per rotation
  → Ensures 4+ weeks between on-call shifts
  → Smaller teams: consider shared rotations across teams
  → Larger teams: split by service domain

Coverage model:
  → Follow-the-sun (3 regions, 8h shifts): best for global teams
  → 24/7 single timezone: requires night shifts, compensate
  → Business hours only + PagerDuty: acceptable for non-critical
```

## Handoff document template

```markdown
# On-Call Handoff — Week of 2026-08-16

## Outgoing: @jane | Incoming: @bob

### Active incidents
- [INC-1234] Payment timeout spike — resolved, monitoring
  for recurrence. Dashboard: [link]
  Action if recurs: restart payment-worker pods

### Known issues
- Alert "disk usage > 80% on db-replica-3" fires daily at 2am.
  Known, storage team expanding volume next week. Acknowledge
  and ignore.
- Staging environment is down (deploy failed Friday).
  Non-urgent, will fix during business hours.

### Upcoming changes
- Tuesday 2pm: database migration (orders table). Expect
  brief latency spike. Runbook: [link]
- Wednesday: marketing email blast (500K). Expect traffic
  spike 10am-12pm.

### Pages this week
- Total: 7 (3 actionable, 4 noise)
- Noise alerts filed for tuning: JIRA-567, JIRA-568

### Handoff checklist
- [ ] PagerDuty rotation transferred
- [ ] On-call Slack channel topic updated
- [ ] Handoff doc reviewed in sync meeting
- [ ] VPN and access verified for incoming on-call
```

## Page quality targets

| Metric | Target | Action if missed |
|---|---|---|
| Pages per week | <10 | Tune alerts, reduce noise |
| Actionable page rate | >80% | Non-actionable = noise, fix the alert |
| Time to acknowledge | <5 min | Review escalation chain |
| MTTR (Mean Time to Resolve) | <1 hour | Improve runbooks |
| Night pages | <2 per week | Defer non-urgent to business hours |
| Interrupt rate (business hours) | <1 per day | Batch low-priority alerts |

```
Alert noise reduction cycle:
  1. Track every page: actionable or noise?
  2. Noise alerts: tune threshold, add context, or delete
  3. Review monthly: are we improving?
  4. Target: every page wakes someone up for a real reason
```

## Compensation and fairness

```
Compensation models:
  → Flat stipend per on-call week ($500-1,500)
  → Per-page bonus for off-hours pages ($50-200 per page)
  → Time-off-in-lieu (TOIL): 1 day off after on-call week
  → Combined: stipend + TOIL (most common in 2026)

Fairness practices:
  → Rotate holidays and weekends fairly (track history)
  → Allow on-call swaps with no manager approval
  → Never assign on-call as punishment
  → Count on-call load in performance reviews (positively)
  → New team members shadow before going primary
```

## Burnout prevention

```
Signals of on-call burnout:
  → Engineer avoids or delays acknowledging pages
  → Quality of incident response declines
  → Engineer requests transfer off the team
  → Sick days increase around on-call weeks
  → Cynicism about alerting ("it's always noise")

Prevention:
  □ Maximum 1 week on-call per 4 weeks
  □ Day off after a week with >5 night pages
  □ No on-call during planned vacation
  □ Retrospective after every on-call week
  □ Alert noise budget: fix 2 noisy alerts per sprint
  □ Runbooks for every alert (no guesswork at 3am)
  □ Escalation path that actually works
```

## Tooling

```
PagerDuty / Opsgenie / Grafana OnCall:
  → Schedule management and rotation
  → Escalation policies
  → Page routing and deduplication
  → On-call analytics (page volume, MTTA, MTTR)

Integration:
  → Alert source → PagerDuty → Slack + phone
  → Auto-create incident channel on page
  → Status page update from incident tool
  → Post-incident review automatically scheduled
```

## Anti-patterns

- **Hero culture** — one senior engineer handling all pages because
  "they're the best at it." This creates a single point of failure,
  prevents junior engineers from learning, and burns out the hero.
  Rotate on-call across all team members with shadowing for juniors.
- **Alert fatigue normalization** — accepting 20+ pages per week as
  normal. High page volume desensitizes on-call engineers, leading
  to slower response times and missed real incidents. Treat alert
  noise as a bug to be fixed.
- **No handoff meeting** — transferring on-call via schedule rotation
  alone with no verbal or written handoff. The incoming on-call has
  no context on active issues, pending changes, or noisy alerts.
  Always do a structured handoff.
- **On-call without runbooks** — expecting engineers to debug
  unfamiliar services at 3am from memory. Every alert should link to
  a runbook with diagnosis steps and remediation actions. No runbook
  = the alert is not ready for production.

## Gotchas

- **Timezone and DST changes** — on-call schedules that span
  timezones must account for daylight saving time transitions. A
  rotation that starts at "9am local time" shifts by an hour twice
  a year, potentially causing gaps or overlaps in coverage.
- **Contractor and part-time on-call** — some jurisdictions require
  on-call time to be counted as working time for compensation
  purposes. Consult employment law before including contractors in
  rotations.
- **On-call during incidents** — if the on-call engineer is also
  the incident commander, they cannot respond to new pages during
  the incident. The secondary must be ready to take over page
  response while primary handles the active incident.
- **Shadow rotations need real pages** — shadowing is only useful
  if the shadow experiences actual pages. Simulate incidents or
  assign during historically busy periods for effective training.

## Verification

- On-call rotation has 4+ engineers with 1-week shifts.
- Handoff document is completed for every rotation transfer.
- Page volume is tracked and stays below 10 per week.
- Actionable page rate exceeds 80%.
- On-call compensation is documented and fair.
- Runbooks exist for every production alert.
- Alert noise is reviewed and reduced monthly.

## Related

- `documentation/docs/policies/lessons/incident-communication-stakeholder-updates.md`
- `documentation/docs/policies/monitoring/alerting-strategy-routing-escalation.md`
- `documentation/docs/policies/lessons/blameless-postmortem-incident-review.md`

## Source URLs (verified 2026-08-16)

- On-Call Rotation Best Practices for Engineering Teams 2026 — https://www.cortex.io/post/on-call-rotation-best-practices
- On-Call Best Practices: Reducing Burnout and Improving Reliability — https://firehydrant.com/blog/on-call-best-practices
- Designing On-Call Rotations That Don't Burn Out Your Team — https://www.pagerduty.com/resources/learn/on-call-rotation-best-practices
- On-Call Compensation: Models and Fairness — https://rootly.com/blog/on-call-compensation-models
