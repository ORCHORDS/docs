---
title: "NIST SP 800-40 Guide to Enterprise Patch Management Planning Template Governance"
standard: "NIST SP 800-40 Rev 4 (Guide to Enterprise Patch Management Planning)"
publisher: "National Institute of Standards and Technology"
category: "governance-template"
subcategory: "vulnerability-and-patch-management"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/40/r4/final"
status: "approved"
classification: "public"
audience: "security-engineering, IT operations, vulnerability management"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-40 Rev 4 — Enterprise Patch Management Planning Template Governance

## Profile

This template governs the recurring, evidence-backed workflow used to plan, prioritise, deploy, verify, and learn from patch cycles across endpoints, servers, network devices, container images, firmware, and SaaS-managed components. It reflects NIST SP 800-40 Rev 4's risk-based, predictability-first framing of patch management as a continuous governance discipline rather than a one-off remediation action.

## Identifier table

| Field | Value |
| --- | --- |
| Standard | NIST SP 800-40 Rev 4 |
| Title | Guide to Enterprise Patch Management Planning |
| Publisher | NIST Computer Security Resource Center |
| Topic | Patch Management Planning |
| Governance role | Enterprise patch policy, risk register, and remediation cadence |

## Scope

The template applies to any organisation that operates production assets exposed to a vulnerability disclosure cycle. It covers:

- Asset inventory alignment so patch targets reconcile against the authoritative configuration management database (CMDB).
- Vulnerability intake from CVE feeds, vendor advisories, internal scanning, bug bounty, and threat intelligence.
- Risk-based prioritisation using exploit availability, exposure, asset criticality, and compensating controls.
- Patch staging, change control, deployment windows, rollback plans, and exception handling.
- Post-deployment verification including health checks, telemetry validation, and unintended-impact review.
- Continuous improvement through metrics, retrospectives, and policy updates.

## Risk-based patch categorisation

NIST SP 800-40 Rev 4 shifts away from rigid severity-only models toward a contextual assessment that combines:

- **Exploit likelihood** — presence of public exploit code, observed in-the-wild exploitation, Metasploit modules, ransomware use, or CISA Known Exploited Vulnerabilities (KEV) listing.
- **Exposure** — whether the asset is internet-facing, handles regulated data, or sits on a privileged network segment.
- **Asset criticality** — business process dependency and recovery time objective.
- **Compensating controls** — virtual patching, network segmentation, WAF rules, or service account isolation that materially reduce risk during the patch window.

The template captures the decision per patch item so that prioritisation is reproducible and audit-defensible.

## Plan / Inputs

- Authoritative asset inventory and ownership map.
- Vulnerability source list (NVD JSON 2.0 feeds, vendor RSS, KEV JSON, internal scanner exports).
- Change calendar and outage windows for business units.
- Rollback artefact inventory (snapshots, golden images, IaC state).
- Communication roster for change advisory board (CAB), incident response, and customer success.

## ORCHORDS Profile table

| ORCHORDS field | Guidance |
| --- | --- |
| Patch cycle name | Concise identifier following the `<system>-<cadence>-<date>` convention. |
| Scope statement | Which asset groups, business units, and geographies are in cycle. |
| Risk tier | Combination of CVSS, exploit availability, asset criticality, exposure. |
| Rollback readiness | Link to validated rollback procedure and most-recent successful test. |
| Verification evidence | Health probe result, synthetic transaction outcome, and log diff summary. |
| Exceptions register | Reference to documented exceptions with compensating control evidence. |

## Implementation Notes

- Treat patch management as a quarterly cadence with emergency fast-track lanes for KEV and ransomware-associated CVEs.
- Maintain a one-page executive summary that shows top risks, deployment progress, and any deviations from plan.
- Couple patch deployment with configuration baseline drift detection so missing patches and out-of-policy settings are visible in the same dashboard.
- Record every patch decision in a structured ticket; do not rely on chat messages or memory.
- Coordinate patch windows with vulnerability scan rescan schedules so coverage is provable.

## Companion Documents

- NIST SP 800-40 Rev 4 (canonical)
- NIST SP 800-128 (Security-Focused Configuration Management)
- CISA Known Exploited Vulnerabilities Catalog
- CVE / NVD JSON 2.0 feed specification
- ISO/IEC 29147 (Vulnerability Disclosure) and ISO/IEC 30111 (Vulnerability Handling)
