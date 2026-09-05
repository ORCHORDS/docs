---
title: "NIST SP 800-137 Information Security Continuous Monitoring Template Governance"
standard: "NIST SP 800-137 (Information Security Continuous Monitoring for Federal Information Systems and Organizations)"
publisher: "National Institute of Standards and Technology"
category: "governance-template"
subcategory: "continuous-monitoring"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/137/final"
status: "approved"
classification: "public"
audience: "security operations, GRC, federal systems integrators"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-137 — Information Security Continuous Monitoring Template Governance

## Profile

This template governs the design and operation of an Information Security Continuous Monitoring (ISCM) programme. It applies NIST SP 800-137's strategy definition, assessment, response, and review cycle so that security posture remains observable, defensible, and responsive to change.

## Identifier table

| Field | Value |
| --- | --- |
| Standard | NIST SP 800-137 |
| Title | Information Security Continuous Monitoring for Federal Information Systems and Organizations |
| Publisher | NIST Computer Security Resource Center |
| Topic | Continuous Monitoring |
| Governance role | ISCM programme governance and assurance reporting |

## Scope

The template covers:

- ISCM strategy definition aligning with organisational risk tolerance and mission priorities.
- Asset, control, and metric selection across people, process, and technology.
- Data collection automation across vulnerability management, configuration, log, and identity systems.
- Analysis and correlation that surface material deviations from expected posture.
- Response and remediation workflows tied to risk register and change management.
- Reporting and review at defined cadences for operational, management, and executive audiences.

## Plan / Inputs

- Risk register and tiered impact classification for systems.
- Control baseline (NIST SP 800-53, ISO/IEC 27001 Annex A, or sector framework).
- Authoritative telemetry catalogue with freshness, accuracy, and integrity notes.
- Onboarding schedule for new assets and decommissioning for retired systems.
- Communication plan for ISCM reports to security operations, GRC, and leadership.

## ORCHORDS Profile table

| ORCHORDS field | Guidance |
| --- | --- |
| Control ID | Identifier of the control being monitored. |
| Monitoring frequency | Continuous, daily, weekly, monthly, quarterly, or on-event. |
| Data source | Authoritative system providing the evidence. |
| Threshold | Acceptable value range; breach triggers escalation. |
| Response action | Owner, action, and SLA tied to deviation. |
| Reporting tier | Operational, management, or executive. |
| Review cycle | Cadence for evaluating the control's continued relevance. |

## Implementation Notes

- Adopt the ISCM strategy with explicit frequency tiers so monitoring cost scales with control criticality.
- Integrate ISCM feeds with the risk register so deviations update organisational risk in near real-time.
- Use standardised data formats (SCAP, OCSF, OpenTelemetry) to reduce integration cost across vendors.
- Document the analyst workflow for triaging ISCM alerts; do not let alerts languish without an owner.
- Re-baseline the ISCM strategy when the threat landscape, control framework, or mission priorities change materially.

## Companion Documents

- NIST SP 800-137 (canonical)
- NIST SP 800-53A Rev 5 (Assessing Security and Privacy Controls)
- NIST SP 800-55 Rev 1 (Performance Measurement Guide for Information Security)
- NIST SP 800-128 (Security-Focused Configuration Management)
- ISO/IEC 27002:2022 control catalogue
- OCSF (Open Cybersecurity Schema Framework)
