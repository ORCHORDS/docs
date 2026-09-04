---
title: "ISO/IEC 42001:2023 AI Management System Version Guide"
standard: "ISO/IEC 42001:2023"
publisher: "International Organization for Standardization (ISO) and International Electrotechnical Commission (IEC)"
category: "reference"
subcategory: "ai-governance"
canonical_url: "https://www.iso.org/standard/81230.html"
status: "approved"
classification: "public"
audience: "AI governance leads, risk officers, certification auditors"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# ISO/IEC 42001:2023 AI Management System (AIMS) Version Guide

## Profile

ISO/IEC 42001:2023 is the first international standard for an AI Management System, published December 2023. It adopts the ISO high-level structure (Annex SL) used by ISO 9001 and ISO 27001, providing a certifiable, auditable framework for establishing, implementing, maintaining, and improving an AI management system across the AI lifecycle.

The standard defines requirements for context (Clause 4), leadership (Clause 5), planning (Clause 6), support (Clause 7), operation (Clause 8), performance evaluation (Clause 9), and improvement (Clause 10). It includes a normative Annex A with control objectives and controls, plus implementation guidance in Annex B and AI-specific terms in Annex C. It is paired with ISO/IEC 42005 (impact assessment) and ISO/IEC 42006 (third-party assessment requirements).

## Identifier

| Field | Value |
| --- | --- |
| Standard | ISO/IEC 42001:2023 |
| Title | Information technology — Artificial intelligence — Management system |
| Publication date | 2023-12 |
| Companion | ISO/IEC 42005 (AI impact assessment), ISO/IEC 42006 (third-party assessment), ISO/IEC 23894 (AI risk management) |
| High-level structure | Annex SL (compatible with ISO 27001 and ISO 9001) |
| Control annex | Annex A — control objectives and controls; Annex B — implementation guidance; Annex C — AI domain terms |

## Clause Map

| Clause | Intent |
| --- | --- |
| 4 — Context | Identify the organization's purpose, issues, requirements, AI system scope, and interested parties. |
| 5 — Leadership | Demonstrate top-management commitment, establish AI policy, assign roles and responsibilities. |
| 6 — Planning | Identify AI risks and opportunities, plan AI risk assessment and impact assessment. |
| 7 — Support | Plan resources, competence, awareness, communication, documented information. |
| 8 — Operation | Operational planning and control, including AI risk assessment, AI risk treatment, and AI system lifecycle controls. |
| 9 — Performance evaluation | Monitoring, measurement, analysis, internal audit, management review. |
| 10 — Improvement | Nonconformity, corrective action, continual improvement. |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | AIMS is treated as the management wrapper over AI RMF 1.0 controls; A Clause may cite AI RMF Core functions for evidence. |
| Statement of Applicability | Required; cross-reference each Annex A control to its applicability and implementation status. |
| AI policy | Documented; reviewed at least annually and on material AI system change. |
| Risk assessment | Use ISO/IEC 23894 as the methodology reference for AIMS Clause 6 / Clause 8 risk assessment. |
| Impact assessment | Use ISO/IEC 42005 as the impact assessment vehicle. |
| Audit | Internal audit at least annually; management review at planned intervals. |
| Documentation | Documented information retention is required by Clause 7.5 and tracked in the Document Control system. |

## Implementation Notes

- The standard does not specify controls for individual AI technologies; it specifies organizational and process controls. Map controls to AI RMF Core functions.
- AIMS is auditable for certification by accredited bodies; certification requires Clause 8 operation evidence.
- Many organizations pair AIMS certification with ISO 27001 certification to address information security across AIMS and ISMS scopes.
- Maintain a single source of truth for AI policy: AIMS does not require separate policies for each AI system.

## Companion Documents

- [ISO/IEC 23894:2023 AI Risk Management Version Guide](ISO_IEC_23894_2023_AI_RISK_VERSION_GUIDE.md)
- [ISO/IEC 42005 AI Impact Assessment Version Guide](ISO_IEC_42005_AI_IMPACT_ASSESSMENT_VERSION_GUIDE.md)
- [NIST AI 100-1 AI RMF 1.0 Version Guide](NIST_AI_100_1_AI_RMF_1_0_VERSION_GUIDE.md)
- [ISO/IEC 27001:2022 ISMS Version Guide](ISO_IEC_27001_2022_ISMS_VERSION_GUIDE.md)
