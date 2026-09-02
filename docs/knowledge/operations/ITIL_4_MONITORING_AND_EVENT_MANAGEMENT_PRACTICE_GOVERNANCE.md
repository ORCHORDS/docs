# ITIL 4 Monitoring and Event Management Practice Governance

## Purpose

Govern the operation of the ITIL 4 monitoring and event management practice so that systems and services are observed systematically, events are classified and correlated deliberately, and only actionable signals reach humans. The practice determines how observation data becomes operational decisions.

## Scope

The practice applies to every production system, platform component, and service the studio operates. It covers event generation, classification, correlation, and escalation into incident or request handling. It does not cover incident response execution (covered by incident management) or SLO policy setting (covered by the SRE service-level objectives practice).

## Workflow

1. Inventory every observable component and define what "healthy" means for it, in measurable terms, before deploying monitoring.
2. Categorize events per the ITIL 4 practice model: information, warning, and exception. Define, in advance, the response owed to each category.
3. Define which events are correlated into a single incident view so that one underlying cause does not page multiple teams.
4. Establish event filtering and suppression rules with owners, rationale, and expiry dates; suppression without an expiry date is prohibited.
5. Route exception events into incident management; route informational events into reporting and trend analysis rather than to on-call staff.
6. Review signal-to-noise metrics for the practice on a recurring cadence and retire alerts that fire without action.
7. Revisit the event taxonomy when architecture changes introduce new component types or new failure modes.

## Controls and evidence

- Event catalogue listing each event source, category, routing, and owner.
- Suppression rule register with rationale, owner, and expiry date for each rule.
- Signal-to-noise and auto-remediation statistics per monitoring domain, reviewed on the practice cadence.
- Practice health review minutes showing decisions to retire, tune, or add alerts.

## Validation

- Sample 10 recent exception events and confirm each reached incident management with correct classification.
- Confirm every suppression rule has an expiry date and a documented rationale.
- Confirm the alert-to-action ratio is measured and reviewed; alerts that never trigger action are candidates for retirement.

## Failure correction

- **Repeated paging for non-actionable events** → reclassify the event, tune or retire the alert, and record the decision in the practice review minutes.
- **Suppression rule with no expiry** → set an expiry date immediately or delete the rule; permanent suppression is not permitted.
- **Correlation gap causing duplicate pages** → add or fix the correlation rule and record the underlying cause in the event catalogue.

## Limitations

- The practice governs observation and routing, not response; its value is realized only when incident management acts on what it produces.
- ITIL 4 defines the practice generically; tool-specific implementations (Alertmanager routing trees, OTel collectors) need their own runbooks.
- Event taxonomies decay as systems evolve; the practice review cadence is the control against decay.

## Scope note

This article is part of the operations leaf and complements the incident management practice and the SRE service-level objectives practice. Cross-reference: `ITIL_4_INCIDENT_AND_PROBLEM_MANAGEMENT_PRACTICE_GOVERNANCE` paths under `itil-4-incident-and-problem-management-practice.md`, `SRE_RELEASE_COORDINATION_ERROR_BUDGET_GOVERNANCE.md`, and `monitoring/README.md`.

## Canonical sources

- AXELOS, *ITIL Foundation, ITIL 4 edition* (2019), monitoring and event management practice: https://www.axelos.com/certifications/itil-service-management
- ITIL 4 Practices — Monitoring and Event Management: https://www.axelos.com/certifications/itil-service-management/itil-4-practices
- NIST SP 800-137 — Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations: https://csrc.nist.gov/publications/detail/sp/800-137/final
- Google SRE Workbook, Chapter 5 — Alerting on SLOs: https://sre.google/workbook/alerting-on-slos/
- OpenTelemetry documentation — Semantic conventions: https://opentelemetry.io/docs/specs/semconv/
