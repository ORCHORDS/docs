# Google SRE SLI/SLO Practice Governance

## 1. Scope
This standard defines how teams select, document, and operate Service
Level Indicators (SLIs) and Service Level Objectives (SLOs) consistent
with Google Site Reliability Engineering (SRE) practice and the
broader observability governance of the platform.

It applies to all user-facing services and any internal service whose
reliability materially affects a user-facing SLO. It does not replace
service-specific reliability targets, which are documented alongside
each service.

## 2. Normative references
The following documents are referenced and inform the requirements of
this standard:

- Google SRE Book, Chapters 4–6 (Service Level Objectives).
- Google SRE Workbook, Chapters 3–5 (SLO engineering).
- W3C Service Level Indicator definition.
- Platform Prometheus and Grafana version governance cards.
- OpenTelemetry Collector Contrib version governance card.

## 3. Terms and definitions
For the purposes of this standard, the following terms apply:

- **Service Level Indicator (SLI)**: a quantitative measure of a
  service's behaviour, expressed as a ratio of good events to total
  events over a measurement window.
- **Service Level Objective (SLO)**: a target value or range for an
  SLI over a defined period.
- **Error budget**: the complement of the SLO target over the period,
  representing the permissible amount of unreliability.
- **Burn rate**: the rate at which the error budget is consumed
  relative to the steady-state allowance.

## 4. SLI selection
SLIs MUST be selected from the four canonical SRE indicator types:
availability, latency, throughput, and freshness. The chosen SLI MUST
reflect user-visible behaviour rather than internal implementation
details. Synthetic probes MUST be used to validate SLI semantics
before production adoption.

## 5. SLO target definition
Each service MUST define at least one SLO with an explicit target,
measurement window, and exclusion policy. SLO targets MUST be derived
from user expectations and historical performance rather than chosen
arbitrarily. Tightening an SLO MUST be accompanied by an explicit
reliability investment plan.

## 6. Error budget policy
Each SLO MUST have an associated error budget policy that defines
alert thresholds, owner responsibilities, and the consequences of
budget exhaustion. Burn-rate alerts MUST trigger at thresholds
documented in the Prometheus alerting adoption playbook.

## 7. Reporting and review
SLI/SLO performance MUST be reviewed at least monthly and the SLO
board MUST be visible to engineering and product owners. Error budget
consumption MUST be reported alongside release readiness decisions.

## 8. Tooling integration
SLI/SLO data MUST be sourced from approved observability backends
(Prometheus, OpenTelemetry Collector, Grafana). New SLI sources MUST
be reviewed by the platform observability owner before adoption.

## 9. Roles and responsibilities
The service owner is accountable for the SLO target and error budget
policy. The platform observability team owns the SLI/SLO tooling and
review cadence. The incident response team owns burn-rate alerting
and budget enforcement.

## 10. Exceptions
Any exception to SLI/SLO practice MUST be approved by the engineering
director responsible for the service and recorded in the SLO
exception register.

## 11. Change management
Material changes to SLI definitions, SLO targets, or error budget
policy MUST follow the platform change management procedure and be
communicated to dependent teams before rollout.

## 12. Audit and evidence
SLI/SLO definitions, dashboards, and burn-rate alert configurations
MUST be retained for at least 24 months in the observability archive
for audit and postmortem use.

## 13. Review cycle
This standard is reviewed at least annually or when a material change
to upstream SRE practice, observability tooling, or error budget
policy occurs.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
