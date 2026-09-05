---
title: "NIST SP 800-128 Guide for Security-Focused Configuration Management Template Governance"
standard: "NIST SP 800-128 (Guide for Security-Focused Configuration Management of Information Systems)"
publisher: "National Institute of Standards and Technology"
category: "governance-template"
subcategory: "configuration-and-baseline-management"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/128/final"
status: "approved"
classification: "public"
audience: "security engineering, IT operations, configuration management"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-128 — Security-Focused Configuration Management Template Governance

## Profile

This template governs the establishment, maintenance, monitoring, and improvement of security-focused configuration baselines across systems. It applies NIST SP 800-128's continuous configuration management model as the operational counterpart to NIST SP 800-53 configuration controls.

## Identifier table

| Field | Value |
| --- | --- |
| Standard | NIST SP 800-128 |
| Title | Guide for Security-Focused Configuration Management of Information Systems |
| Publisher | NIST Computer Security Resource Center |
| Topic | Configuration Management |
| Governance role | Baseline governance and configuration drift management |

## Scope

The template covers:

- Baseline definition (operating systems, applications, cloud services, network devices, container images).
- Configuration item (CI) inventory and ownership.
- Change control through authorised, reviewed, and tested modifications.
- Configuration monitoring for drift detection against approved baselines.
- Exception handling and deviation documentation.
- Configuration management automation, including infrastructure-as-code and policy-as-code.

## Plan / Inputs

- Authoritative asset inventory with classification and ownership.
- Baseline source catalogue (CIS Benchmarks, DISA STIGs, vendor hardening guides, internal standards).
- Change advisory board process and emergency change procedure.
- Drift detection tooling and notification policy.
- Exception register with compensating control evidence.

## ORCHORDS Profile table

| ORCHORDS field | Guidance |
| --- | --- |
| Configuration item | Identifier and owner of the managed entity. |
| Baseline version | Specific baseline release applied to the CI. |
| Deviation | Difference between observed and baseline configuration. |
| Risk rating | Criticality of the deviation to the system's security posture. |
| Exception reference | Identifier of approved exception with expiry. |
| Remediation action | Owner, action, and target completion date. |
| Verification evidence | Policy-as-code result, scanner output, or manual attestation. |

## Implementation Notes

- Anchor baselines in vendor hardening guides and CIS Benchmarks; tailor only when risk analysis supports deviation.
- Express baselines as machine-readable policy (SCAP, OVAL, Rego, Cloud Custodian) to enable continuous evaluation.
- Treat configuration drift as an event, not a slow-accumulating condition; detect, triage, and remediate on defined SLAs.
- Pair configuration management with vulnerability and patch programmes so the same dashboard reflects both posture and risk.
- Version baselines and store them in source control with code review and approval evidence.

## Companion Documents

- NIST SP 800-128 (canonical)
- NIST SP 800-53 CM family (Configuration Management controls)
- NIST SP 800-70 Rev 5 (Guide to Mapping ICT Products to Security Baselines)
- NIST SP 800-40 (Guide to Enterprise Patch Management Planning)
- CIS Benchmarks and DISA STIGs
- SCAP / OVAL specifications
