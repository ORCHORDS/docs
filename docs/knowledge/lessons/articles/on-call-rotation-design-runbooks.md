# On-Call Rotation Design and Runbooks

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

On-call engineers burn out after weeks of nightly pages.
Incidents are misrouted because escalation paths are
tribal knowledge. New team members get added to the
rotation before they have runbooks to follow, so every
page becomes a crisis.

## Context

A sustainable on-call programme requires three things:
a rotation schedule that distributes cognitive load
fairly, escalation policies that are machine-enforced,
and runbooks that let any rotation member resolve the
most common pages without heroics. This entry codifies
the patterns the platform team uses and why.

## 1. Rotation Schedule Patterns

Three patterns are common in engineering organisations.
Choose based on team geography and team size.

```
+------------------+----------+-----------------------+
| Pattern          | Min team | Best for              |
+------------------+----------+-----------------------+
| Weekly           |    4     | Co-located teams,     |
|                  |          | low alert volume      |
+------------------+----------+-----------------------+
| Biweekly         |    6     | Teams where context   |
|                  |          | switch cost is high   |
+------------------+----------+-----------------------+
| Follow-the-sun   |   8+     | Globally distributed, |
| (12-hour shifts) |          | high alert volume     |
+------------------+----------+-----------------------+
```

Cognitive load target: no engineer should receive more
than 5 actionable pages per 12-hour shift on average.
Track this in the on-call log (see section 5). If the
rate exceeds the target for two consecutive rotations,
treat it as a reliability incident and schedule a toil
reduction sprint.

Avoid rotations shorter than one week unless your alert
volume genuinely requires follow-the-sun; context
switches increase time-to-resolve.

## 2. PagerDuty / OpsGenie Rotation Config

Set up the schedule as code where possible and commit it
to the infrastructure repository.

```yaml
# terraform-pagerduty example
resource "pagerduty_schedule" "primary" {
  name      = "payment-api-primary"
  time_zone = "UTC"

  layer {
    name                         = "weekly-rotation"
    start                        = "2026-01-06T00:00:00Z"
    rotation_virtual_start       = "2026-01-06T00:00:00Z"
    rotation_turn_length_seconds = 604800   # 7 days

    users = [
      pagerduty_user.alice.id,
      pagerduty_user.bob.id,
      pagerduty_user.carol.id,
      pagerduty_user.dan.id,
    ]
  }
}
```

For OpsGenie, export rotation YAML and store it in
`infra/oncall/schedules/`:

```yaml
# opsgenie-schedule.yaml
name: payment-api-primary
timezone: UTC
rotation:
  type: weekly
  startDate: "2026-01-06T00:00:00Z"
  participants:
    - alice@example.com
    - bob@example.com
    - carol@example.com
    - dan@example.com
```

Ensure the secondary schedule mirrors the primary but
is offset by one position so the next person in the
rotation becomes backup automatically.

## 3. Handoff Template

The outgoing engineer must complete the handoff before
their rotation ends. Store completed handoffs in the
team wiki under `oncall/handoffs/YYYY-MM-DD.md`.

```
# On-Call Handoff — [Date]

Outgoing:  [name]
Incoming:  [name]
Period:    [start] – [end]

## Systems in Scope
- payment-api (prod)      — primary owner
- notification-worker     — secondary coverage

## Open Incidents
| ID   | Title                        | Status    | Owner |
|------|------------------------------|-----------|-------|
| INC-  | DB connection pool spikes   | monitored | alice |

## Known Flappiness
- payment-api: latency alert fires ~03:00 UTC on
  batch job nights; safe to acknowledge if p99 < 800 ms
  and error rate is normal.

## Runbook Changes This Week
- Runbook #12 updated: added step for pool exhaustion.

## Toil Count This Rotation
- Actionable pages: 14
- False positives:   3
- Manual tasks:      7

## Notes for Incoming
- Scheduled maintenance window: 2026-08-20 02:00 UTC
- Carol is on PTO; Dan is backup secondary.
```

## 4. Escalation Policy

Encode escalation in your alerting platform and never
rely on people remembering the chain.

```
Level 1 — Primary On-Call
  Notified immediately via phone + push.
  Response SLA: 5 minutes.

Level 2 — Secondary On-Call
  Notified if Level 1 has not acknowledged in 5 min.
  Response SLA: 10 minutes from initial page.

Level 3 — Engineering Manager / Tech Lead
  Notified if Level 2 has not acknowledged in 10 min.
  Authorised to escalate to vendor support, invoke
  DR plan, or call in additional engineers.

Level 4 — VP Engineering
  Notified automatically for any P1 that crosses
  the 30-minute mark without resolution.
```

Define "acknowledged" in the tool, not just in policy.
In PagerDuty, acknowledged means the engineer has
clicked the ack button — not that they have read Slack.

## 5. Toil Tracking in the On-Call Log

Log every page, not just the critical ones. Use a
lightweight structured format so you can query it.

```
| Date       | Alert name            | Actionable | Toil | Notes         |
|------------|-----------------------|------------|------|---------------|
| 2026-08-12 | HighMemoryUsage       | yes        | yes  | manual restart|
| 2026-08-13 | CertExpirySoon        | no         | no   | auto-renewed  |
| 2026-08-14 | PaymentTimeoutSpike   | yes        | no   | auto-resolved |
```

Aggregate monthly:
- Toil ratio = toil pages / actionable pages
- If toil ratio > 50 %, schedule a reliability sprint.
- False positive rate = non-actionable / total pages.
- Target false positive rate < 20 %.

## 6. On-Call Compensation and Sustainability

On-call time is work. Establish clear policy before
engineers join the rotation.

Common models:
- Flat weekly stipend (simplest, most common).
- Per-page compensation above a threshold.
- Time-in-lieu for pages outside business hours.

Regardless of model, every engineer on rotation must
have at least 8 consecutive hours off in every 24-hour
period and at least one full weekend off per month.
Track this programmatically using schedule data.

Maximum sustainable rotation size is 4 engineers at
low-volume services and 6+ for high-volume services.
Smaller rotations create burnout; larger ones erode
familiarity with the systems.

## Anti-patterns

- Adding engineers to the rotation on day one before
  they have completed runbook training.
- Treating every alert as equal urgency — severity
  levels exist for a reason; do not page for warnings.
- Skipping handoffs during holidays; these are the
  moments when institutional knowledge matters most.
- Creating runbooks that require production database
  access to execute; runbooks must be safe for
  read-only access unless the step is explicitly marked
  "privileged — approve before executing."

## Gotchas

- Follow-the-sun requires clear overlap windows of at
  least 30 minutes; ambiguous handoff times cause
  unclaimed incidents.
- OpsGenie on-call overrides do not always sync with
  downstream integrations; test overrides in staging.
- A rotation of fewer than 4 engineers means each
  person is on-call roughly every fourth week, which
  is sustainable; fewer than 3 is not.
- Time zones in PagerDuty schedules affect when the
  rotation turns over; confirm the display timezone
  matches what engineers expect.

## Verification

1. Trigger a test alert in staging and confirm the
   correct primary is paged within 60 seconds.
2. Let the acknowledgement timeout expire and confirm
   the secondary is paged.
3. Review the last two months of on-call logs and
   verify toil ratio and false positive rate are within
   targets.
4. Confirm the current handoff document exists in the
   team wiki and is dated within the last 7 days.

## Related

- `documentation/docs/policies/lessons/on-call-rotation-best-practices.md`
- `documentation/docs/policies/lessons/incident-handoff-cross-timezone.md`
- `documentation/docs/policies/lessons/alert-fatigue-masks-real-outages-2026.md`
- `documentation/docs/policies/lessons/write-the-runbook-before-the-incident.md`
- `documentation/docs/policies/lessons/incident-responder-support.md`

## Source URLs (verified 2026-08-17)

- https://sre.google/workbook/on-call/
- https://www.pagerduty.com/resources/learn/on-call-management/
- https://docs.opsgenie.com/docs/rotation-based-schedules
- https://increment.com/on-call/on-call-at-any-size/
