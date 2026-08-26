# On-Call Rotation Best Practices

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your on-call rotation burns out engineers. The same few people always end
up handling incidents. Night pages interrupt sleep regularly, and the team
dreads their rotation week. On-call handoffs are informal, with no
context passed between shifts. Incident response quality drops during
weekends and holidays because responders are unfamiliar with the systems
they are covering.

## Context

On-call rotations ensure 24/7 incident response for production systems.
A well-designed rotation balances coverage requirements with engineer
well-being. In 2026, research consistently shows that sleep disruption
from on-call work has cumulative health effects, and companies that
invest in sustainable on-call practices see 30-40% less burnout-related
attrition. The shift toward AI-assisted incident triage is reducing
unnecessary pages, but humans remain essential for complex, novel failure
modes.

## Rotation models

### Weekly rotation

The most common model. One engineer is primary on-call for a full week
(Monday to Monday).

| Pros | Cons |
|---|---|
| Simple to schedule | A bad week exhausts the responder |
| Full context over the week | Long recovery needed after high-incident weeks |
| Fewer handoffs | Uneven burden if some weeks are worse than others |

### Follow-the-sun

Teams in different time zones cover their business hours only. No single
engineer is paged at night.

| Pros | Cons |
|---|---|
| No nighttime pages | Requires teams in 2-3 time zones |
| Sustainable long-term | Handoff complexity increases |
| Better response quality (alert responders) | Harder to coordinate for small orgs |

### Split-day rotation

Divide the day into 12-hour shifts (e.g., 8am-8pm and 8pm-8am). Night
shifts rotate more frequently to distribute the burden.

### Hybrid model

Primary on-call handles all alerts. Secondary on-call is an escalation
path for complex issues and covers if the primary is unreachable
(15-minute escalation timer).

## Rotation sizing

**Minimum 3 people per rotation.** With fewer than 3, engineers are
on-call too frequently (every other week with 2 people) and cannot take
vacation without disrupting coverage. For sustainable rotations:

| Rotation size | On-call frequency | Sustainability |
|---|---|---|
| 2 people | Every other week | Unsustainable — burnout in months |
| 3-4 people | Every 3-4 weeks | Minimum viable |
| 5-6 people | Every 5-6 weeks | Sustainable |
| 7+ people | Monthly or less | Ideal, allows growth and vacations |

## Page management

### Alert quality

The single most important factor in on-call quality. Every page should
be **actionable** — requiring a human to do something that cannot be
automated.

```
Good alert:  "Payment processing error rate > 5% for 5 minutes"
             → Responder investigates payment provider, retries, or fails over

Bad alert:   "Disk usage > 70%"
             → Not urgent, should be a ticket, not a page
             → Or: auto-scale should handle this
```

### Alert fatigue thresholds

| Metric | Healthy | Warning | Critical |
|---|---|---|---|
| Pages per shift | < 2 | 2-5 | > 5 |
| Night pages per week | 0-1 | 2-3 | > 3 |
| Alert noise ratio | < 10% | 10-30% | > 30% |
| Time to acknowledge | < 5 min | 5-15 min | > 15 min |

If any metric is in the critical zone, the rotation is unsustainable and
engineering investment in alert quality or automation is required before
adding more engineers.

## Compensation and recovery

### Compensation models

| Model | Description | Common in |
|---|---|---|
| **Flat stipend** | Fixed amount per on-call shift | US tech companies |
| **Per-page bonus** | Additional payment per incident response | European companies (labor law) |
| **Comp time** | Time off after on-call week | Companies with flexible PTO |
| **Combined** | Stipend + comp time | Best practice |

### Recovery time

After a high-incident on-call shift (3+ nighttime pages):
- Next business day should be lighter (no meetings before noon).
- If paged after midnight, the engineer should start late or take a half
  day the next day.
- Managers should track cumulative on-call burden per engineer per quarter.

## Handoff practices

### Start-of-rotation handoff

The outgoing on-call engineer should provide:

```
1. Active incidents (open, mitigated, monitoring)
2. Known risks (deploy scheduled, traffic spike expected, flaky test)
3. Recent changes (deploys in last 48h, infrastructure changes)
4. Maintenance windows (scheduled downtime, vendor maintenance)
5. Runbook updates (new or modified runbooks since last rotation)
```

### Handoff medium

- Written summary in a shared channel (Slack, Teams) at rotation start.
- 15-minute live handoff for complex situations.
- On-call log (a running document updated during the shift with incident
  notes and context).

## Anti-patterns

- **Hero culture** — one engineer who "handles everything" and never
  delegates. This creates a single point of failure and prevents the
  team from developing incident response skills.
- **No escalation path** — primary on-call with no secondary or
  management escalation. A single responder overwhelmed by a major
  incident has no relief.
- **Volunteer-only on-call** — asking for volunteers instead of assigning
  rotations. The same people always volunteer, creating inequity. Others
  never develop production awareness.
- **Paging for non-urgent issues** — using the on-call pager for things
  that could wait until business hours (log noise, non-critical warnings,
  batch job delays). This trains responders to ignore alerts.

## Gotchas

- **Timezone-aware scheduling** — rotation schedules must account for
  daylight saving time transitions. A weekly rotation that starts at
  "9am local time" shifts by an hour twice a year unless handled.
- **Holiday coverage** — plan holiday rotations at least a month in
  advance. Offer incentives (extra comp, preferred scheduling) for
  holiday coverage. Never assume the default rotation covers holidays
  without explicit agreement.
- **On-call during interviews** — being on-call affects interview
  performance. Avoid scheduling interviews during on-call weeks.
- **Regulatory requirements** — some jurisdictions (EU Working Time
  Directive) have legal limits on on-call hours. Consult legal before
  establishing rotation patterns in regulated markets.

## Verification

- Rotation has a minimum of 3 engineers.
- Page volume is tracked and reviewed monthly (target: < 2 per shift).
- Written handoff happens at every rotation change.
- Compensation or comp time is provided for on-call shifts.
- Post-incident recovery time is granted after high-incident shifts.
- Alert noise ratio is measured and action items created for noisy alerts.

## Related

- `documentation/categories/lessons/blameless-postmortem-incident-review.md`
- `documentation/categories/monitoring/frontend-real-user-monitoring-rum.md`
- `documentation/categories/worktree/incident-communication-runbook-templates.md`

## Source URLs (verified 2026-08-16)

- PagerDuty on-call guide — https://www.pagerduty.com/resources/learn/call-rotations-schedules/
- Incident.io on-call best practices — https://incident.io/blog/on-call-best-practices
- Atlassian on-call handbook — https://www.atlassian.com/incident-management/on-call
- Google SRE on-call chapter — https://sre.google/sre-book/being-on-call/
