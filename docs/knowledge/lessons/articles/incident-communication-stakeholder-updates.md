# Incident Communication and Stakeholder Updates

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Engineering is working the incident while customers, executives,
and support teams are left in the dark. The status page goes
40 minutes without an update. Internal stakeholders flood the
incident Slack channel asking "what's happening?" — diverting
engineers from diagnosis. Each update is written from scratch
under pressure, with inconsistent tone, detail, and timing.
After resolution, the status page says "resolved" with no
explanation and no follow-up report.

## Context

Incident communication is part of incident response, not a
separate activity. Manual status updates pull engineers away
from diagnosis; every minute spent drafting an executive email
is a minute not spent on the fix. Modern incident platforms
(incident.io, PagerDuty, Statuspage) automate communication
workflows so updates are a byproduct of incident state changes,
not a separate task. The standard update cadence — every 30
minutes for Sev 1, every 60 minutes for Sev 2 — applies
whether or not there is new information to report.

## Audience matrix and channels

```
Audience      Needs                  Channel         Timing
────────────────────────────────────────────────────────────
Customers     Is it down?            Status page,    <5 min of
              When resolved?         email           impact confirm

Support       What to tell callers,  Slack channel,  Immediate
              workarounds            internal status

Engineering   Technical details,     Incident Slack  Real-time
              blast radius, owners   channel

Executives    Business impact,       Slack DM,       Within 15 min,
              customer count, ETA    email           then hourly
```

## Update cadence

```
Severity 1 (critical — full or major outage):
  → Status page: every 15–30 minutes
  → Internal Slack: every 10 minutes
  → Executive summary: at detection + every 30 minutes
  → Post-incident report: within 48 hours

Severity 2 (degraded service — partial impact):
  → Status page: every 30–60 minutes
  → Internal Slack: every 30 minutes
  → Executive summary: on detection and resolution only
  → Post-incident report: within 5 business days

Severity 3 (minor — low user impact):
  → Status page: on detection and resolution only
  → Internal: team channel only

The rule: if 30 minutes has passed and there is nothing
new to say, publish: "We are continuing to investigate.
No new information at this time. Next update in 30 min."
Silence erodes trust faster than any update.
```

## Status page update templates

```
Initial detection (within 5 minutes of confirmed impact):

  Title: [Service] — Investigating increased error rates

  We are investigating reports of [symptom: slow page
  loads, failed API calls] affecting [service name].
  We will provide an update within 30 minutes.

  Start time: [HH:MM UTC] | Affected: [component list]

Resolution (as soon as monitoring confirms clean):

  Title: [Service] — Resolved

  The issue affecting [service] has been resolved.
  All systems are operating normally.

  Duration: [start]–[end] ([X hr Y min])
  Root cause: [one sentence, non-technical]

  We will publish a detailed incident report by [date].
  We apologize for the disruption.
```

## Language that builds trust vs language that erodes it

```
Trust-building:
  "We have identified the likely cause."
  "The impact affected approximately X% of users."
  "We made an error in our deployment process."
  "Here is what we are doing to prevent recurrence."

Trust-eroding:
  "We are experiencing some issues." (vague, dismissive)
  "Due to unforeseen circumstances..." (deflects blame)
  Technical jargon: "a Kafka consumer group rebalanced"
    (customers want what broke, not how it works)

The test for each sentence: does it answer "what broke,
who is affected, and when will it be fixed?" If not,
cut it.
```

## Post-incident communications

```
Post-incident report (within 48 hr for Sev 1,
                      within 5 days for Sev 2):
  Audience: customers (public) and internal stakeholders.
  Sections:
    1. Summary (2–3 sentences)
    2. Timeline (UTC timestamps, key events)
    3. Root cause (non-technical first; technical
       addendum for engineering audience)
    4. Remediation (what was done to restore service)
    5. Prevention (specific action items with owners
       and due dates — not "we will improve monitoring")

  Publish a preliminary report before the postmortem is
  complete. A draft with honest facts builds more trust
  than silence while the review is in progress.
```

## Anti-patterns

- **Silent incidents** — acknowledging the issue internally
  but not updating the status page. Customers detect the
  impact regardless. Publish within 5 minutes of confirming
  customer-visible impact.
- **Cadence breaks during long incidents** — going silent
  for two hours during an extended outage. Even if nothing
  has changed, publish on schedule with a holding update.
- **Promising a postmortem and not delivering it** —
  committing to a 48-hour report and missing it damages
  trust more than the original incident itself.
- **Single-channel communication** — relying only on the
  status page. Use automated routing: support needs Slack,
  executives need email, customers need the status page.

## Gotchas

- **Status page must be hosted independently** — if your
  primary infrastructure is down, your status page must
  stay up. Use a separate provider or CDN-hosted static
  page.
- **Subscriber notification flooding** — too-frequent
  updates (every 5 minutes) flood inboxes and train
  subscribers to ignore them. Follow the severity cadence.
- **All-clear is not the end** — the post-incident report
  commitment must be tracked. Add it to the incident
  tracker immediately on resolution with a due date.

## Verification

- Status page updated within 5 minutes of confirmed
  customer-visible impact for all Sev 1 and Sev 2 events.
- Update cadence matches severity table.
- Status page hosted on infrastructure independent of
  primary production systems.
- Post-incident reports published within committed
  timeframes for all Sev 1 events in the past quarter.

## Related

- `documentation/docs/policies/lessons/blameless-postmortem-incident-review.md`
- `documentation/docs/policies/lessons/on-call-rotation-best-practices.md`
- `documentation/docs/policies/lessons/incident-response-runbook.md`
- `documentation/docs/policies/monitoring/alerting-strategy-routing-escalation.md`

## Source URLs (verified 2026-08-17)

- incident.io Incident Communication Best Practices — https://incident.io/blog/incident-communication-best-practices
- Atlassian Statuspage Documentation — https://support.atlassian.com/statuspage/
- Cloudflare Incident Communication Model — https://blog.cloudflare.com/incident-response/
- PagerDuty Incident Communication Guide — https://www.pagerduty.com/resources/learn/incident-communication/
- How to Write an Incident Postmortem — https://www.atlassian.com/incident-management/postmortem
