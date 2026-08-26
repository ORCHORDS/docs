# SLO Implementation — Error Budgets, Burn-Rate Alerting, and Release Gating

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team tracks uptime as "number of nines" but has no formal
mechanism to decide when reliability work takes priority over
features. An SLI drops to 99.85% for three days but nobody notices
because the single-window alert threshold is set at 99.5%. When
the quarterly review reveals the SLO was missed, the discussion
becomes blame-oriented because there is no objective budget to
point to. Meanwhile, a latency regression ships because the
deployment pipeline has no reliability gate.

## Context

An SLI (Service Level Indicator) is a quantitative measure of
service behavior (e.g., successful requests / total requests). An
SLO (Service Level Objective) is a target threshold on that SLI
over a compliance window (typically 28 or 30 days). The error budget
is `1 - SLO`: at 99.9% over 30 days, that is ~43.2 minutes of
allowed badness; at 99.95% it is ~21.6 minutes. The jump from three
nines to 3.5 nines halves the budget, which is why teams should
justify each additional nine against real user and business impact
rather than picking round numbers. Google's SRE Workbook established
multi-window, multi-burn-rate alerting as the standard approach for
SLO-based monitoring.

## SLI types

```
SLI Type       Measurement                   Example
──────────────────────────────────────────────────────────────
Availability   good_events / valid_events    Non-5xx / total
               (non-error responses)          requests

Latency        % requests under threshold    95% of requests
               (histogram buckets, NOT        < 300ms
               raw averages)

Throughput     Requests processed vs          Jobs completed /
               expected or queued             jobs submitted

Correctness    Data/output validity checks    % pipeline records
                                              passing schema
                                              validation
```

## Error budget calculation

```
SLO Target    Error Budget (30 days)    Monthly Downtime
──────────────────────────────────────────────────────────────
99%           1%                        ~7.3 hours
99.5%         0.5%                      ~3.6 hours
99.9%         0.1%                      ~43.2 minutes
99.95%        0.05%                     ~21.6 minutes
99.99%        0.01%                     ~4.3 minutes

Burn rate = (SLI error rate) / (1 - SLO)

  Burn rate 1.0  → exhausts budget exactly at period end
  Burn rate 14.4 → exhausts 30-day budget in ~1 hour
  Burn rate 6.0  → exhausts 30-day budget in ~5 hours
  Burn rate 3.0  → exhausts 30-day budget in ~10 days
```

## Multi-window burn-rate alerting

```
Google SRE Workbook pattern:

  Uses paired short + long windows per severity tier:
    Short window: confirms the problem is CURRENT
    Long window: confirms it is SIGNIFICANT
    Both must breach simultaneously to fire.
    Short window is typically 1/12th of long window.

  Severity    Budget    Long    Short    Burn Rate
              consumed  window  window   threshold
  ──────────────────────────────────────────────────
  Page        2%        1h      5m       14.4x
  Page        5%        6h      30m      6x
  Ticket #<number>%       24h     2h       3x
  Ticket #<number>%       72h     6h       1x

  Why multi-window:
    Single short window → fast but noisy (spikes)
    Single long window  → quiet but slow to detect
    Both together       → fast detection, low noise
```

## Sloth configuration (Prometheus)

```yaml
# sloth.yml — generates Prometheus recording + alert rules
version: "prometheus/v1"
service: "checkout-api"
labels:
  team: "payments"
slos:
  - name: "requests-availability"
    objective: 99.9
    description: "99.9% of checkout requests succeed"
    sli:
      events:
        error_query: >
          sum(rate(http_requests_total{job="checkout",
          code=~"5.."}[{{.window}}]))
        total_query: >
          sum(rate(http_requests_total{job="checkout"}
          [{{.window}}]))
    alerting:
      name: CheckoutHighErrorRate
      page_alert:
        labels:
          severity: page
      ticket_alert:
        labels:
          severity: ticket
```

```
Sloth auto-generates:
  → Prometheus recording rules for SLI ratios
  → Multi-window burn-rate alert rules
  → Both page and ticket severity alerts
  → Can ingest OpenSLO YAML directly
```

## Tools and specifications

```
Tool/Spec       Type              Notes
──────────────────────────────────────────────────────────────
Sloth           Prometheus SLO    Generates recording + alert
                generator         rules from YAML spec

OpenSLO         Vendor-neutral    GitOps-friendly YAML spec,
                specification     reached 1.0

Nobl9           Commercial SLO    Founding OpenSLO contributor,
                platform          multi-source aggregation

Dynatrace       APM with SLO     Built-in burn rate monitoring,
                                  release-gating quality gates

Google Cloud    SLO Monitoring    Native SLO tracking in
                                  Cloud Monitoring
```

## SLO-based release gating

```
Pattern:
  1. Check error budget before deployment
  2. If budget exhausted or burn rate > threshold:
     → Block non-critical feature releases
     → Require incident postmortem or exec sign-off
     → Redirect engineering to reliability work
  3. If budget healthy:
     → Proceed with deployment
     → Monitor burn rate post-deploy for rollback signal

  Implementation:
    → Budget-check API gate in CD pipeline
    → Quality gates that block/rollback on post-deploy spikes
    → Dynatrace: "SLO-driven quality gates for BizDevOps"
```

## Consequences of budget exhaustion

```
Typical escalation policy:

  1. Halt non-critical feature releases
  2. Redirect engineering capacity to reliability work
  3. Require additional review/approval for risky changes
  4. Reduce release cadence (daily → weekly)
  5. Escalate to engineering leadership
  6. Resume normal velocity when burn rate normalizes

  Key: consequences must be documented and agreed upon
  BEFORE the budget is exhausted. Without predefined
  consequences, SLO practice becomes toothless.
```

## Anti-patterns

- **Averaging latency instead of using percentiles** — a mean
  of 200ms hides a p99 of 5 seconds. Use histogram buckets and
  percentile-based SLIs for latency.
- **SLOs on infrastructure metrics** — CPU utilization and memory
  usage are not user-facing outcomes. Define SLIs from the user's
  perspective (request success, response time).
- **Too many nines without customer justification** — 99.99%
  sounds impressive but costs 10x the engineering effort of 99.9%.
  Match the SLO to actual customer expectations and business impact.
- **Single-window alerting** — either too slow to detect (long
  window) or too noisy from spikes (short window). Use the
  multi-window, multi-burn-rate pattern from the SRE Workbook.
- **No consequences for budget exhaustion** — defining SLOs
  without agreed-upon consequences when the budget runs out makes
  the entire practice performative.

## Gotchas

- **"Valid events" denominator matters** — exclude client errors
  (4xx from bad user input) from the error count. A spike in 400s
  from a bot should not consume your error budget.
- **Compliance window choice** — 28-day rolling windows are more
  predictable than calendar months (no short-February effect).
  Google SRE recommends rolling windows.
- **Budget is shared across all failure modes** — planned
  maintenance, deployments, and incidents all consume the same
  budget. Account for planned downtime when setting targets.
- **SLO ≠ SLA** — SLOs are internal engineering targets. SLAs are
  external contractual commitments with financial penalties. SLOs
  should be stricter than SLAs to provide a buffer.

## Verification

- SLIs defined from user-facing behavior (availability, latency).
- SLO targets justified against customer expectations.
- Error budgets calculated with documented consequences.
- Multi-window burn-rate alerting configured (page + ticket).
- Sloth or equivalent generates Prometheus recording rules.
- Release pipeline includes error-budget gate.
- 28-day rolling compliance window used.

## Related

- `documentation/docs/policies/monitoring/distributed-tracing-sampling-strategies.md`
- `documentation/docs/policies/monitoring/alerting-strategy-noise-reduction.md`
- `documentation/docs/policies/monitoring/opentelemetry-collector-pipeline-config.md`

## Source URLs (verified 2026-08-16)

- Google SRE Workbook — Alerting on SLOs — https://sre.google/workbook/alerting-on-slos/
- Sloth SLO Spec Reference — https://sloth.dev/specs/default/
- Nobl9 — OpenSLO in Action — https://www.nobl9.com/resources/open-slo-yaml-code
- Dynatrace — SLO Concepts and Error-Budget Burn Rate — https://docs.dynatrace.com/docs/deliver/service-level-objectives/service-level-objective-basics
