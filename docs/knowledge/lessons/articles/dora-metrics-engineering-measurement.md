# DORA Metrics and Engineering Measurement

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Engineering leadership asks "are we shipping faster than last
quarter?" and nobody can answer with data. Deployment frequency
is inferred from Jira ticket counts. MTTR after a major incident
comes from calendar math and memory. A proposal to invest in
CI/CD has no baseline to justify it. Teams report story points
as a velocity proxy but cannot connect technical throughput to
business outcomes or detect when accumulated debt is slowing
delivery down.

## Context

The DORA (DevOps Research and Assessment) four key metrics are
the industry standard for measuring software delivery performance,
published annually since 2018 by Google's DORA Research Program.
They correlate with organizational outcomes: elite-performing
teams deploy 127x more frequently, recover 2,293x faster, and
have 3x lower change failure rates than low performers. The 2024
DORA Report found that AI-assisted coding improves code quality
by +7.5% but decreases delivery stability by -7.2%, which means
the four metrics must be monitored together. The SPACE framework
(Satisfaction, Performance, Activity, Communication, Efficiency)
was introduced as a complement that captures developer experience
dimensions the four metrics miss.

## The four metrics and elite benchmarks

```
Metric             What it measures       Elite       Low
──────────────────────────────────────────────────────────────
Deployment         Frequency of           Multiple    <1 per
Frequency          production deploys     per day     6 months

Lead Time          Commit to              <1 hour     >6 months
for Changes        production deploy

Change Failure     Deploys causing a      <5%         >30%
Rate               production incident

MTTR               Detect to restore      <1 hour     >1 week
                   for production
```

Measure MTTR from first customer-visible impact, not from
incident declaration. The gap between the two inflates the
apparent metric and masks monitoring blind spots.

## Instrumenting the four metrics

```
Deployment Frequency:
  Source: CD pipeline events (Argo CD, GitHub Actions)
  Instrument: emit a "deployment completed" event per
  environment; filter to production only.
  Pitfall: counting commits or PR merges instead of
  production deploy events inflates the number.

Lead Time for Changes:
  Source: commit timestamp + deployment event timestamp.
  Instrument: tag each deployment with the commit SHA(s)
  it contains; calculate median time from first commit
  in the batch to deploy completion.
  Pitfall: measuring from PR open date excludes pre-review
  work. Use commit timestamp.

Change Failure Rate:
  Source: deployment events + incident events.
  Formula: incidents caused by deployment /
           total deployments in the same window.
  Pitfall: not all incidents are deployment-caused. Require
  a "triggered by deployment" flag on incidents and audit
  it in retrospectives.

MTTR:
  Source: incident management tool with accurate
  first-impact and resolution timestamps.
  Pitfall: measuring from incident declaration rather than
  from monitoring alert or first user report.
```

## SPACE framework as complement

```
Dimension      What it captures
──────────────────────────────────────────────────────
Satisfaction   Wellbeing, job satisfaction (survey)
Performance    Quality, reliability outcomes
Activity       Volume: commits, PRs, reviews
Communication  PR review latency, documentation use
Efficiency     Flow: context switches, wait times

Use SPACE when:
  → DORA looks healthy but teams report feeling slow
  → AI adoption is happening and you need to isolate
    its effect on individual developer experience
  → Burnout signals appear despite high deploy frequency
```

## Tooling

```
Category           Tools
──────────────────────────────────────────────────────
DORA-native        LinearB, Jellyfish, Sleuth, Faros
Broad DevEx        DX (getdx.com), Swarmia, Cortex
Self-hosted        Four Keys (Google open-source),
                   GitHub + BigQuery pipeline
Incident-MTTR      PagerDuty, incident.io, OpsGenie
```

## Anti-patterns

- **Gaming Deployment Frequency** — splitting one logical
  change into many small deployments to inflate the count.
  The signal is batch size and cycle time, not raw deploy
  count. Watch for single-line-change deploys as a pattern.
- **Measuring Lead Time from PR open** — code in review
  has already been written. Lead time from commit to deploy
  reflects actual delivery speed; PR open date excludes
  pre-review work and understates throughput.
- **Using DORA as performance reviews** — teams optimize
  the metric, not the outcome. DORA metrics are diagnostic,
  not evaluative. Never attach compensation or ratings to
  individual DORA scores.
- **Survey-based data collection** — asking teams to self-
  report deployment frequency introduces recall bias and
  gaming. Instrument the CD pipeline directly.

## Gotchas

- **Elite benchmarks are medians, not targets** — "multiple
  deploys per day" is median for elite performers overall.
  For B2B SaaS with enterprise change control, daily
  deployments is an elite result. Calibrate to context.
- **DORA does not measure business impact** — high deploy
  frequency with wrong features destroys value. Pair DORA
  with OKRs or outcome metrics to close the loop.
- **The 2024 AI paradox** — AI coding assistants raise code
  quality metrics but lower delivery stability, likely
  because higher velocity introduces more change risk.
  Monitor CFR and MTTR when rolling out AI tools.
- **Microservice inflation** — 200 microservices can show
  1,000+ deploys per day without shipping user features
  faster. Segment deployment frequency by product surface.

## Verification

- Deployment events instrumented in the CD pipeline and
  filtered to production only.
- Lead time calculated from commit timestamp, not PR open
  date, using pipeline correlation.
- Change Failure Rate incidents tagged with deployment
  trigger flag in the incident management system.
- MTTR measured from first customer-visible impact using
  monitoring alert timestamps.
- DORA trends reviewed in quarterly engineering health
  reviews alongside developer satisfaction data.
- SPACE survey results reviewed alongside DORA dashboard
  each quarter.

## Related

- `documentation/docs/policies/lessons/technical-debt-measurement-prioritization.md`
- `documentation/docs/policies/lessons/blameless-postmortem-incident-review.md`
- `documentation/docs/policies/lessons/feature-flag-lifecycle-management.md`
- `documentation/docs/policies/monitoring/alerting-strategy-routing-escalation.md`

## Source URLs (verified 2026-08-17)

- DORA 2024 State of DevOps Report — https://dora.dev/research/2024/dora-report/
- Four Keys (Google open-source project) — https://github.com/dora-team/fourkeys
- SPACE Framework (ACM Queue) — https://queue.acm.org/detail.cfm?id=3454124
- LinearB DORA Metrics Guide — https://linearb.io/blog/dora-metrics
- DORA Metrics Tools in 2026 — https://getdx.com/blog/dora-metrics-tools/
