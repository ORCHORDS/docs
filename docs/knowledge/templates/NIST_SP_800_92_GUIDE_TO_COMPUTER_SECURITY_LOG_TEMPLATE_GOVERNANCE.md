---
title: "NIST SP 800-92 Guide to Computer Security Log Management Template Governance"
standard: "NIST SP 800-92 (Guide to Computer Security Log Management)"
publisher: "National Institute of Standards and Technology"
category: "governance-template"
subcategory: "logging-and-audit"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/92/final"
status: "approved"
classification: "public"
audience: "security operations, platform engineering, audit"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-92 — Computer Security Log Management Template Governance

## Profile

This template governs log management planning, collection, retention, analysis, and protection across the enterprise. It applies NIST SP 800-92's guidance for organising log infrastructure as a first-class operational capability rather than an after-the-fact artefact of system operation.

## Identifier table

| Field | Value |
| --- | --- |
| Standard | NIST SP 800-92 |
| Title | Guide to Computer Security Log Management |
| Publisher | NIST Computer Security Resource Center |
| Topic | Log Management |
| Governance role | Logging programme and audit trail governance |

## Scope

The template covers:

- Log source inventory, owner mapping, and event-type catalogue.
- Collection, normalisation, and transport (syslog, OCSF, OpenTelemetry, vendor agents).
- Storage tiers with retention, integrity protection, and legal hold support.
- Analysis workflow including correlation rules, anomaly detection, and triage queues.
- Protection of log infrastructure against tampering, unauthorised access, and loss.
- Disposal and archival aligned with regulatory and litigation obligations.

## Plan / Inputs

- Authoritative list of in-scope systems with their event sources and owners.
- Regulatory retention matrix (PCI DSS, GDPR, HIPAA, SOX, sector-specific rules).
- Storage tier budget and integrity controls (WORM, hashing, signed audit trails).
- Analyst capacity model for monitoring, deep-dive, and incident support.
- Disposal schedule with legal review checkpoint.

## ORCHORDS Profile table

| ORCHORDS field | Guidance |
| --- | --- |
| Source system | Component emitting log events, with owner and environment. |
| Event class | Authentication, authorisation, data access, system change, network, application-specific. |
| Criticality | High, medium, low based on investigative and audit value. |
| Retention tier | Hot, warm, cold, archive, with deletion date. |
| Integrity control | Hash chain, digital signature, or WORM with auditor verification. |
| Review cadence | Daily, weekly, monthly, or on-demand per source. |
| Disposal authority | Named role empowered to approve deletion. |

## Implementation Notes

- Prefer structured event formats (JSON, OCSF, CEF) over unstructured syslog to enable correlation.
- Centralise time synchronisation under NTP/PTP with documented accuracy targets; log time skew is a frequent root cause of failed correlation.
- Separate log write paths from log read paths so analysts cannot tamper with evidence even with administrative access.
- Maintain a written policy covering log generation, transmission, storage, and disposal that the audit team can attest to.
- Treat privacy obligations as a first-class constraint when designing log content; redact or hash personal data where feasible.

## Companion Documents

- NIST SP 800-92 (canonical)
- NIST SP 800-137 (Information Security Continuous Monitoring)
- OCSF (Open Cybersecurity Schema Framework) specification
- PCI DSS Requirement 10 (logging)
- ISO/IEC 27001 Annex A 8.15 (Logging)
- ISO/IEC 27037 (Identification, collection, acquisition and preservation of digital evidence)
