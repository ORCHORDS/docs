# Incident Communication and Runbook Templates

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

When a SEV1 incident hits, engineers scramble to write stakeholder updates
from scratch. The incident commander is pulled between coordinating the
response and drafting customer communications. There are no pre-written
templates, no defined escalation paths, and post-incident reviews are
inconsistent. Mean time to acknowledge (MTTA) and mean time to resolve
(MTTR) suffer because communication overhead competes with engineering
time.

## Context

Incident communication and runbooks are complementary tools. Runbooks
define repeatable, structured response workflows for specific failure
modes — the technical steps. Communication templates define the
stakeholder-facing messaging — the updates, status pages, and post-
incident reports. Both must be findable in under 30 seconds by any on-call
engineer, linked directly to monitoring alerts.

## Runbook structure

A well-structured runbook contains:

```
## Runbook: [Alert Name]

### Metadata
- Owner: [Team]
- Last reviewed: [Date]
- Linked alert: [Alert URL]
- Severity: SEV1/SEV2/SEV3

### Symptoms
What the engineer will see — the alert text, dashboard state, user reports.

### Immediate actions (first 5 minutes)
1. Verify the alert is real (not a monitoring false positive)
2. Check [dashboard URL] for scope of impact
3. Escalate to [Slack channel] if SEV1/SEV2

### Diagnosis steps
Step-by-step investigation with exact commands:
- `kubectl get pods -n production | grep CrashLoopBackOff`
- `SELECT count(*) FROM orders WHERE created_at > now() - interval '5m'`

### Remediation
- Option A: Rollback deployment — `./scripts/rollback.sh production`
- Option B: Scale up — `kubectl scale deployment api --replicas=10`
- Option C: Feature flag disable — toggle [flag name] in LaunchDarkly

### Verification
How to confirm the issue is resolved:
- Error rate on [dashboard] drops below 0.1%
- [Health check URL] returns 200

### Escalation
- If unresolved after 30 minutes: page [Senior Engineer]
- If customer-facing: notify [Comms Lead] for status page update
```

## Communication templates

### Template 1: Initial status page update (within 15 minutes)

```
Title: [Service] — Degraded Performance / Partial Outage / Major Outage

We are investigating reports of [brief symptom — e.g., "elevated error
rates on the API" / "inability to process payments"]. Our engineering team
is actively working on a resolution.

Impact: [Who is affected and how — e.g., "Users may experience timeouts
when accessing the dashboard."]

Next update: We will provide an update within 30 minutes.
```

### Template 2: Ongoing update (every 20-30 minutes for SEV1)

```
Update [N] — [Time UTC]

Status: [Investigating / Identified / Monitoring / Resolved]

We have identified the issue as [brief root cause]. Our team is
[current action — e.g., "rolling back the deployment" / "scaling
infrastructure"]. We expect resolution within [estimate or "we are still
assessing"].

Impact: [Updated impact — e.g., "Approximately 15% of API requests are
failing."]

Next update: [Time of next update]
```

### Template 3: Resolution update

```
Resolved — [Time UTC]

[Service] is operating normally. The issue was caused by [brief root
cause]. We [action taken — e.g., "rolled back the deployment and applied
a fix"]. We will publish a detailed post-incident review within 72 hours.

Duration: [Start time] to [End time] ([total duration])
```

## Role separation during incidents

| Role | Responsibility |
|---|---|
| **Incident Commander** | Coordinates response, approves communications, manages escalation |
| **Communications Lead** | Drafts and sends all stakeholder updates (status page, Slack, email) |
| **Technical Lead** | Diagnoses and remediates the technical issue |
| **Scribe** | Maintains the incident timeline in the incident channel |

Engineers focused on resolution must never be pulled away to write
stakeholder updates — that is the communications lead's job.

## Post-incident review template

```
## Post-Incident Review: [Incident Title]

**Date:** [Date]
**Severity:** SEV[1/2/3]
**Duration:** [Total duration]
**Impact:** [Users affected, revenue impact, SLO burn]

### Timeline
- [HH:MM UTC] — Alert fired: [alert name]
- [HH:MM UTC] — Engineer acknowledged
- [HH:MM UTC] — Root cause identified
- [HH:MM UTC] — Fix deployed
- [HH:MM UTC] — Monitoring confirmed resolution

### Root cause
[Clear, systemic description — not "human error"]

### Contributing factors
- [Factor 1 — e.g., "No circuit breaker on the payment gateway"]
- [Factor 2 — e.g., "Deployment lacked canary phase"]

### Action items
| Action | Owner | Deadline | Status |
|---|---|---|---|
| Add circuit breaker to payment gateway | Payments team | [Date] | Open |
| Add canary deployment step to pipeline | Platform team | [Date] | Open |

### Lessons learned
[What went well, what didn't, what was surprising]
```

## Anti-patterns

- **No templates** — writing communications from scratch under pressure
  leads to inconsistent, incomplete, or delayed updates.
- **Engineers writing comms** — context-switching between debugging and
  writing status updates slows both.
- **Vague action items** — "improve monitoring" is not actionable. Every
  action item needs an owner, specific deliverable, and deadline.
- **Runbooks in wikis nobody reads** — runbooks must be linked directly
  to alerts. If the alert fires and the runbook is more than one click
  away, it won't be used.
- **Stale runbooks** — a runbook that hasn't been reviewed after the last
  incident involving that alert is unreliable. Review after every use.

## Gotchas

- **Multi-timezone incidents** — standardize all timestamps in UTC. Local
  times in incident timelines cause confusion during handoffs.
- **Customer vs. internal comms** — status page updates are public-facing
  and must avoid internal jargon. Internal Slack updates can be technical.
- **Legal review for major incidents** — data breaches and incidents
  involving customer data may require legal review before public
  communication. Build this into the SEV1 escalation path.
- **Alert fatigue** — if runbooks are linked to alerts that fire
  frequently and are always false positives, engineers stop reading them.
  Fix the alert first.

## Verification

- Every production alert has a linked runbook.
- Runbooks are reviewed after each incident and at least quarterly.
- Communication templates are accessible in the incident response tool.
- Post-incident reviews are published within 72 hours.
- Action items from post-incident reviews have owners and deadlines.
- Incident response roles are documented and practiced in drills.

## Related

- `documentation/categories/monitoring/golden-signals-monitoring.md`
- `documentation/categories/monitoring/slo-error-budget-alerting.md`
- `documentation/categories/lessons/automated-incident-response.md`

## Source URLs (verified 2026-08-16)

- Rootly runbook guide — https://rootly.com/incident-response/runbooks
- incident.io runbook automation — https://incident.io/blog/runbook-automation-tools-2026-the-complete-guide
- incident.io postmortem best practices — https://incident.io/blog/sre-incident-postmortem-best-practices
- ITOC360 communication guide — https://www.itoc360.com/incident-communication/
