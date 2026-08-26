# Alerting Strategy, Routing, and Escalation

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your on-call engineers are paged for non-critical issues at 3am. Alert
fatigue has set in — the team ignores many alerts because most are false
positives or low priority. There is no clear escalation path when the
primary on-call cannot resolve an issue. Different monitoring tools
(Datadog, Prometheus, CloudWatch) each send alerts through different
channels with inconsistent severity levels. You cannot answer "how many
actionable alerts did we have last week?" without manual counting.

## Context

An alerting strategy defines what to alert on, who to alert, how to
route alerts, and when to escalate. In 2026, the alerting landscape has
consolidated around incident management platforms (PagerDuty, Grafana
OnCall, incident.io) that centralize alert routing, deduplication, and
escalation from multiple monitoring sources. The key principle remains:
every alert must be actionable — if the on-call engineer cannot take a
specific action to resolve it, the alert should not exist.

## Alert severity levels

| Severity | Response | Example | Channel |
|---|---|---|---|
| **P1 — Critical** | Immediate (< 5 min) | Service outage, data loss | Page (phone call + push) |
| **P2 — High** | Urgent (< 30 min) | Degraded performance, partial outage | Page (push notification) |
| **P3 — Medium** | Business hours | Elevated error rate, approaching threshold | Slack channel |
| **P4 — Low** | Next sprint | Warning threshold, capacity planning | Ticket/email |

### Severity classification rules

```
P1: Revenue-impacting outage, data loss, security breach
    → Page the on-call immediately, escalate after 15 min
P2: Degraded user experience, single-service failure with fallback
    → Page the on-call, escalate after 30 min
P3: Non-customer-facing issue, approaching a threshold
    → Post to Slack, review in daily standup
P4: Informational, capacity planning, optimization opportunity
    → Create a ticket, prioritize in sprint planning
```

## Alert routing architecture

```
Monitoring sources           Alert router              Responders
┌──────────────┐            ┌─────────────┐
│  Datadog     │───────────►│             │──► Team A on-call (payments)
│  Prometheus  │───────────►│  PagerDuty  │──► Team B on-call (platform)
│  CloudWatch  │───────────►│  or OnCall  │──► Team C on-call (frontend)
│  Custom      │───────────►│             │──► Escalation (engineering lead)
└──────────────┘            └─────────────┘
```

### Service-based routing

```yaml
# PagerDuty service configuration (conceptual)
services:
  - name: Payment Processing
    team: payments-team
    escalation:
      - level: 1
        targets: [payments-oncall]
        timeout: 15m
      - level: 2
        targets: [payments-lead, engineering-manager]
        timeout: 30m
      - level: 3
        targets: [vp-engineering]

  - name: API Gateway
    team: platform-team
    escalation:
      - level: 1
        targets: [platform-oncall]
        timeout: 15m
      - level: 2
        targets: [platform-lead]
```

## Alert quality framework

### Actionable alert checklist

Every alert should answer:
1. **What** is happening? (Clear description, not just a metric name)
2. **Why** does it matter? (Business impact)
3. **What** should the responder do? (Link to runbook)
4. **How urgent** is it? (Severity/priority)

```
Bad:  "CPU > 80% on web-server-3"
Good: "API response time degraded (P2): p99 latency > 2s for /checkout
       endpoint for 5+ minutes. 500 users affected. Likely cause: database
       connection pool exhaustion. Runbook: https://wiki/runbooks/api-latency"
```

### Alert hygiene metrics

| Metric | Target | Action if exceeded |
|---|---|---|
| Alerts per on-call shift | < 2 | Review and reduce noisy alerts |
| Alert noise ratio (non-actionable / total) | < 10% | Tune thresholds or delete |
| Mean time to acknowledge (MTTA) | < 5 min | Review notification channels |
| Alerts auto-resolved before ack | < 20% | Increase alert duration threshold |
| Duplicate/correlated alerts | 0 | Configure deduplication rules |

## Deduplication and correlation

### Alert deduplication

```
Alert: "Database CPU > 90%" at 14:01
Alert: "Database CPU > 90%" at 14:02
Alert: "Database CPU > 90%" at 14:03
→ Deduplicate: one incident, three occurrences
```

### Alert correlation

```
Alert: "Database CPU > 90%" at 14:01
Alert: "API latency > 2s" at 14:02
Alert: "Checkout error rate > 5%" at 14:03
→ Correlate: one incident (database overload), three symptoms
```

Most incident management platforms support dedup keys and alert
grouping rules to prevent alert storms from creating dozens of
independent pages.

## Platform comparison

| Feature | PagerDuty | Grafana OnCall | incident.io |
|---|---|---|---|
| Alert routing | Service + event rules | Routes + escalation chains | Alert routes |
| Escalation | Multi-level, timed | Multi-level, timed | Multi-level |
| On-call scheduling | Built-in | Built-in | Built-in |
| Deduplication | Dedup key + intelligent | Grouping rules | Alert grouping |
| Integrations | 700+ | Grafana ecosystem | 50+ |
| Pricing | $21-49/user/mo | Free (OSS) or Cloud | Per-user |
| Incident management | Built-in (basic) | Separate | Built-in (advanced) |

## Anti-patterns

- **Alert on every metric** — creating alerts for CPU, memory, disk,
  and network on every host produces hundreds of alerts per day. Alert
  on user-facing symptoms (latency, errors, availability), not causes.
- **No runbook links** — an alert without a runbook link forces the
  responder to search for documentation during an incident. Every alert
  should link to its resolution procedure.
- **Flat escalation** — all alerts go to the same person or channel
  with no escalation path. When the on-call is unavailable or
  overwhelmed, alerts go unacknowledged.
- **Alerting on recoverable conditions** — auto-scaling events,
  transient network blips, and self-healing pod restarts do not need
  human intervention. Alert only when automated remediation fails.

## Gotchas

- **Maintenance windows** — schedule maintenance windows in your
  alerting platform to suppress expected alerts during deployments,
  database maintenance, and infrastructure changes.
- **Alert threshold hysteresis** — setting alert and recovery thresholds
  at the same value (e.g., alert at 80% CPU, recover at 80% CPU) causes
  flapping. Use hysteresis (alert at 80%, recover at 70%).
- **Cross-team alert routing** — an alert that requires coordination
  between teams (frontend + backend) needs a clear primary owner.
  Routing to multiple teams simultaneously causes diffusion of
  responsibility.
- **Time-of-day routing** — some alerts are P2 during business hours
  but P3 after hours. Configure time-based severity or suppression
  rules to avoid unnecessary nighttime pages.

## Verification

- Every alert has a severity level, owner, and runbook link.
- Alert noise ratio is measured monthly (target: < 10%).
- Escalation policies are configured for all critical services.
- Deduplication rules prevent alert storms.
- On-call engineers report alert quality in retrospectives.
- Unused or noisy alerts are reviewed and pruned quarterly.

## Related

- `documentation/categories/lessons/on-call-rotation-best-practices.md`
- `documentation/categories/monitoring/synthetic-monitoring-uptime-checks.md`
- `documentation/categories/lessons/blameless-postmortem-incident-review.md`

## Source URLs (verified 2026-08-16)

- PagerDuty alerting best practices — https://drdroid.io/engineering-tools/best-practices-for-alerting-using-pagerduty
- OpsGenie alerting best practices — https://drdroid.io/engineering-tools/best-practices-for-alerting-using-opsgenie
- Monitoring and alerting to reduce fatigue — https://oneuptime.com/blog/post/2026-02-20-monitoring-alerting-best-practices/view
- Escalation policy comparison — https://incident.io/blog/escalation-policy-tools-comparison
