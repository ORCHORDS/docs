# DORA — Digital Operational Resilience Act Engineering Compliance

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your financial services application handles payments, trading, or
insurance but has no formalized ICT risk management framework. Auditors
ask for evidence of resilience testing, incident reporting timelines,
and third-party risk assessments, and your engineering team scrambles
to produce documentation retroactively. You cannot demonstrate to
regulators which services are critical, who owns them, how failures are
detected, or how quickly incidents are resolved.

## Context

The EU Digital Operational Resilience Act (DORA), Regulation (EU)
2022/2554, became fully applicable on 17 January 2025. It consolidates
and harmonizes ICT risk requirements across the EU financial sector,
covering credit institutions, investment firms, insurance undertakings,
payment institutions, and crypto-asset service providers. In 2026,
regulators have moved from reviewing paperwork to demanding proof —
real-time evidence of resilience, automated reporting, and demonstrable
control over ICT risk. The engineering burden is substantial: teams must
show auditors which services exist, who owns them, how failures are
detected, and how quickly incidents are resolved — with evidence, not
assertions.

## DORA's five pillars

```
1. ICT Risk Management
   → Identify, classify, and document all ICT assets
   → Continuous monitoring and vulnerability management
   → Change management with impact assessment

2. ICT Incident Reporting
   → Classify incidents by severity and impact
   → Report major incidents to regulators within 4 hours
   → Intermediate report within 72 hours, final within 1 month

3. Digital Operational Resilience Testing
   → Basic testing: vulnerability scanning, network security
   → Advanced testing: Threat-Led Penetration Testing (TLPT)
   → TLPT required every 3 years for significant entities

4. ICT Third-Party Risk Management
   → Maintain register of all ICT third-party providers
   → Assess concentration risk (single provider dependency)
   → Exit strategies for critical providers

5. Information Sharing
   → Voluntary sharing of cyber threat intelligence
   → Participation in industry information-sharing arrangements
```

## Engineering requirements

### 1. Service catalog and ownership

```yaml
# Every service must be documented
services:
  - name: payment-gateway
    criticality: critical
    owner: payments-team
    slo:
      availability: 99.95%
      latency_p99: 200ms
    dependencies:
      - stripe-api (third-party)
      - postgres-primary (internal)
    on_call: payments-oncall
    runbook: https://wiki/runbooks/payment-gateway
    recovery_time_objective: 15m
    recovery_point_objective: 1m
```

### 2. Incident classification and reporting

| Severity | Criteria | Reporting timeline |
|---|---|---|
| Major | ≥ 10% of clients affected, or financial loss > threshold, or data breach | Initial: 4 hours, Intermediate: 72 hours, Final: 1 month |
| Significant | Degraded service, limited client impact | Internal reporting, no regulatory obligation |
| Minor | No client impact, resolved quickly | Internal tracking only |

### 3. Resilience testing requirements

```
Basic testing (all entities, annually):
  □ Vulnerability scanning (automated, continuous)
  □ Network security assessments
  □ Open-source software analysis (SBOM)
  □ Gap analysis against standards
  □ Source code review for critical applications
  □ Scenario-based testing (failover, DR)
  □ Compatibility testing
  □ Performance testing

Advanced testing (significant entities, every 3 years):
  □ Threat-Led Penetration Testing (TLPT)
  □ Based on TIBER-EU framework
  □ Conducted by qualified external testers
  □ Covers critical functions and systems
  □ Results shared with regulators
```

### 4. Third-party risk register

```
For each ICT third-party provider:
  □ Provider name, jurisdiction, subcontractors
  □ Services provided and data processed
  □ Criticality assessment (critical or important)
  □ Concentration risk (sole provider for critical function?)
  □ Exit strategy and data portability plan
  □ Contractual provisions (audit rights, SLAs)
  □ Last assessment date and findings
```

## Engineering controls checklist

| Control area | Evidence required | Tooling |
|---|---|---|
| Asset inventory | Complete service catalog | Port, Backstage, ServiceNow |
| Monitoring | SLO dashboards, alerting configs | Datadog, Grafana, PagerDuty |
| Incident response | Runbooks, on-call schedules | PagerDuty, incident.io |
| Change management | PR reviews, deployment logs | GitHub, ArgoCD |
| Access control | IAM policies, MFA evidence | Okta, AWS IAM |
| Backup/recovery | RTO/RPO test results | Automated DR drills |
| Vulnerability mgmt | Scan reports, patch timelines | Snyk, Dependabot, Trivy |
| Penetration testing | TLPT reports | External testers |
| Third-party risk | Vendor register, SLA reports | Vanta, Drata |

## Anti-patterns

- **Documentation-only compliance** — writing policies without
  implementing controls. DORA requires evidence that controls work,
  not just that they are documented. Automate evidence collection.
- **Annual testing only** — running vulnerability scans and resilience
  tests once a year. DORA requires continuous monitoring and regular
  testing. Integrate security scanning into CI/CD pipelines.
- **Ignoring third-party concentration risk** — relying on a single
  cloud provider or payment processor without exit strategies. DORA
  explicitly requires concentration risk assessment and documented
  exit plans for critical providers.
- **Treating DORA as a compliance team problem** — DORA compliance
  requires engineering teams to build and maintain controls. Auditors
  ask for deployment logs, incident timelines, and monitoring configs
  — artifacts that only engineering can produce.

## Gotchas

- **Scope includes crypto-asset service providers** — if your
  platform handles crypto assets under MiCA, DORA applies to your
  ICT systems. This is broader than traditional financial regulation.
- **Subcontractor chain** — DORA requires visibility into your
  providers' subcontractors. A cloud provider using a third-party CDN
  creates a chain that must be documented and assessed.
- **TLPT coordination** — Threat-Led Penetration Testing must be
  coordinated with the relevant financial supervisor. The test scope,
  methodology, and results must be shared with regulators.
- **Cross-border complexity** — entities operating across multiple EU
  member states must comply with DORA at the group level. National
  supervisors may have additional requirements.

## Verification

- Complete service catalog with ownership, SLOs, and runbooks.
- Incident classification framework with regulatory reporting
  timelines.
- Automated vulnerability scanning runs in CI/CD pipelines.
- Third-party ICT provider register is maintained and reviewed
  quarterly.
- Resilience testing (failover, DR) runs at least annually.
- Evidence collection is automated (deployment logs, incident
  timelines, monitoring configs).

## Related

- `documentation/docs/policies/compliance/soc2-type-ii-audit-preparation.md`
- `documentation/docs/policies/lessons/blameless-postmortem-incident-review.md`
- `documentation/docs/policies/monitoring/alerting-strategy-routing-escalation.md`

## Source URLs (verified 2026-08-16)

- DORA Compliance 2026 Key Requirements — https://digital.nemko.com/regulations/digital-operational-resilience-act
- EU DORA Compliance for Engineering Teams — https://www.port.io/blog/navigating-the-eus-digital-operational-resilience-act-eu-dora
- DORA Digital Operational Resilience Act Guide — https://blog.dorapp.eu/digital-operational-resilience/dora-digital-operational-resilience-act
- DORA Compliance Guide 2026 — https://www.orbiqhq.com/eu-regulations/dora-compliance
