# Alerting fatigue reduction strategies

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Engineers silence entire alert channels because pages arrive faster
than they can be triaged. An on-call engineer acknowledges a page,
takes no action, and goes back to sleep — the alert was noise. MTTA
climbs not from slow engineers but because most pages self-resolve.
Critical incidents are then missed inside the noise floor.

## Context

Alert fatigue is a structural failure, not a staffing problem. When
actionable-alert rate drops below 80 %, on-call culture degrades
within weeks. Root causes are consistent: alerts trigger on internal
symptoms rather than user impact, thresholds are copy-pasted without
calibration, no single team owns a rule, and there is no scheduled
cadence to review rule quality. Fixing fatigue requires data-driven
triage, clear ownership, burn-rate semantics, and a hard distinction
between pages and tickets.

## Signal-to-noise measurement

Tag every fired alert: **actionable** (led to a change), **noise**
(auto-resolved or ignored), or **informational** (opened a ticket).

| Metric              | Target   | Danger zone |
|---------------------|----------|-------------|
| Actionable rate     | ≥ 90 %   | < 80 %      |
| MTTA                | < 5 min  | > 15 min    |
| Noise alerts/shift  | < 5      | > 20        |
| False-positive rate | < 10 %   | > 25 %      |

Run a 30-day alert audit quarterly. Any rule with a noise rate above
20 % must be fixed or deleted before the next rotation begins.

## Multi-window burn-rate alerting

Raw-threshold alerts fire and recover faster than engineers can
respond. Burn-rate alerts measure budget consumption velocity.
Pair each rule with a long window (1 h or 6 h) and a short
confirmation window (5 min or 30 min). The alert fires only when
both exceed the threshold simultaneously.

```yaml
# Fast burn — 2 % of monthly error budget in 1 h — page
- alert: ErrorBudgetBurnHighFast
  expr: |
    (job:slo_error_rate:ratio_rate5m{job="api"} > (14.4 * 0.001))
    and
    (job:slo_error_rate:ratio_rate1h{job="api"} > (14.4 * 0.001))
  for: 2m
  labels:
    severity: page
    owner: platform
  annotations:
    runbook_url: https://runbooks.example.com/api-burn-rate

# Slow burn — 10 % in 6 h — ticket, not page
- alert: ErrorBudgetBurnSlow
  expr: job:slo_error_rate:ratio_rate6h{job="api"} > (6 * 0.001)
  for: 15m
  labels:
    severity: ticket
    owner: platform
  annotations:
    runbook_url: https://runbooks.example.com/api-burn-rate
```

## Alert ownership and runbook links

Every alert rule must carry an `owner` label and a `runbook_url`
annotation. An alert without a runbook is non-actionable by
definition. Runbook minimum content: what triggered this, what to
check first, escalation path, rollback steps. Lint `runbook_url`
for HTTP 200 in CI. One team owns each rule; shared ownership is
no ownership.

## Pages vs tickets and grouping

| Class  | Criteria                        | Delivery      |
|--------|---------------------------------|---------------|
| Page   | User-visible outage now         | Phone / app   |
| Ticket | Budget depleting slowly         | Jira / Linear |
| Log    | Informational, no action        | Logging only  |

Ticket-class alerts must never route to PagerDuty. Use inhibition
rules to suppress downstream symptom alerts when a root-cause alert
is already active.

```yaml
# Alertmanager: group by root cause, inhibit downstream
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
inhibit_rules:
  - source_match: {alertname: DatabaseDown}
    target_match_re: {alertname: (ApiHighErrorRate|ApiLatency.*)}
    equal: ['cluster']
```

## On-call rotation health

Track per-engineer page load across rotations. If variance exceeds
2×, re-balance. If the mean exceeds three pages per shift, run a
triage sprint against the alert backlog. Schedule alert review as
protected calendar time — monthly minimum, weekly for fast-growth
services.

## Anti-patterns

- **CPU/memory threshold alerts without user impact** — fires
  constantly, never actionable; replace with SLO burn-rate alerts.
- **Silencing rather than fixing** — silences must carry an expiry
  date and a linked issue; they mask real problems otherwise.
- **Alert copy-paste without calibration** — templates never match
  actual traffic; always tune thresholds against real data.
- **Runbook links that 404** — enforce HTTP 200 lint in CI; a
  broken URL wastes critical minutes during an incident.

## Gotchas

- Burn-rate alerting requires a defined SLO period (30 days is
  standard); without one the multiplier is undefined.
- `group_wait` set too short fires before related alerts arrive,
  producing incomplete groups and duplicate pages.
- Multi-window alerting can fail silently if the short-window metric
  has scrape gaps; monitor scrape health separately.
- Alert review cadence must be scheduled time, not an aspirational
  backlog item that gets dropped when incidents pile up.

## Verification

- Noise rate below 10 % over the trailing 30-day window.
- Every alert rule has `owner` label and valid `runbook_url`.
- `runbook_url` links return HTTP 200 in CI lint job.
- Pages-only queue contains zero ticket-class alert routes.
- Alertmanager inhibition rules verified in staging via fault
  injection before each major infrastructure change.

## Related

- `documentation/docs/policies/monitoring/slo-multi-window-alerting.md`
- `documentation/docs/policies/monitoring/on-call-rotation-setup.md`
- `documentation/docs/policies/monitoring/alert-grouping-patterns.md`
- `documentation/docs/policies/monitoring/alerting-runbook-linking.md`
- `documentation/docs/policies/monitoring/escalation-policy-design.md`

## Source URLs (verified 2026-08-17)

- Google SRE Workbook — Alerting on SLOs —
  https://sre.google/workbook/alerting-on-slos/
- Alertmanager configuration reference —
  https://prometheus.io/docs/alerting/latest/configuration/
- PagerDuty on-call health guide —
  https://www.pagerduty.com/resources/learn/on-call-health/
- Atlassian runbook best practices —
  https://www.atlassian.com/incident-management/runbook
