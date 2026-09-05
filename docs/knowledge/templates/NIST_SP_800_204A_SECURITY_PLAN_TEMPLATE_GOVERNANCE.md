---
title: "NIST SP 800-18 Rev 1 Guide for Developing Security Plans for Federal Information Systems Template Governance"
standard: "NIST SP 800-18 Rev 1 (Guide for Developing Security Plans for Federal Information Systems)"
publisher: "National Institute of Standards and Technology"
category: "governance-template"
subcategory: "system-security-planning"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/18/r1/final"
status: "approved"
classification: "public"
audience: "system owners, security engineering, GRC, federal systems integrators"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-18 Rev 1 — System Security Plan Template Governance

## Profile

This template governs the creation and maintenance of System Security Plans (SSPs) that document how a system meets its security requirements. It applies NIST SP 800-18 Rev 1's guidance for aligning SSPs with NIST SP 800-53 controls, the Risk Management Framework, and the system's authorisation boundary.

## Identifier table

| Field | Value |
| --- | --- |
| Standard | NIST SP 800-18 Rev 1 |
| Title | Guide for Developing Security Plans for Federal Information Systems |
| Publisher | NIST Computer Security Resource Center |
| Topic | System Security Planning |
| Governance role | SSP development, review, and approval |

## Scope

The template covers the structure and content of an SSP, including:

- System identification, owner, and authorisation boundary.
- System environment, architecture, and data flow.
- System categorization using FIPS 199 (low, moderate, high impact).
- Control selection, tailoring, and implementation status.
- Continuous monitoring strategy and plan of action and milestones integration.
- Review, approval, and update cadence.

## Plan / Inputs

- Authoritative asset and service inventory for the system.
- FIPS 199 categorisation with documented rationale.
- Control baseline selection (NIST SP 800-53 low, moderate, or high).
- Risk assessment and applicable overlays (NIST SP 800-53B).
- Stakeholder roster for SSP review, including the Authorising Official.

## ORCHORDS Profile table

| ORCHORDS field | Guidance |
| --- | --- |
| System identifier | Unique identifier for the system and its boundary. |
| System owner | Named individual accountable for the SSP. |
| Categorisation | FIPS 199 security objectives with impact levels. |
| Control implementation status | Implemented, partially implemented, planned, alternative, or not applicable. |
| Tailoring rationale | Justification for any deviation from the baseline. |
| Monitoring strategy | Link to the ISCM plan and frequency tiers. |
| Review cadence | Annual or risk-driven SSP refresh schedule. |

## Implementation Notes

- Treat the SSP as a living artefact; update it whenever control status, ownership, or boundary changes.
- Align control descriptions with concrete implementation evidence — configurations, runbooks, and screenshots — to support assessment.
- Capture inherited controls explicitly to avoid duplication and clarify which entity is responsible.
- Coordinate SSP review with the Authorising Official so authorisation decisions are based on current content.
- Cross-reference the SSP with the Plan of Action and Milestones (POA&M) so remediation items remain traceable.

## Companion Documents

- NIST SP 800-18 Rev 1 (canonical)
- NIST SP 800-53 Rev 5 (Security and Privacy Controls)
- NIST SP 800-53B (Control Baselines)
- FIPS Publication 199 (Standards for Security Categorization)
- NIST Risk Management Framework (RMF)
- NIST SP 800-37 Rev 2 (Risk Management Framework for Information Systems and Organizations)
