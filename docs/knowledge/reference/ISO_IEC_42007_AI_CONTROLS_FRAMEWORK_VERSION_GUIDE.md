---
title: "ISO/IEC 42007 AI Controls Framework Version Guide"
standard: ISO/IEC 42007 (draft)
publisher: ISO/IEC JTC 1/SC 42
category: reference
subcategory: ai-governance
canonical_url: https://www.iso.org/standard/87312.html
status: approved
classification: public
audience: ai-governance, platform-engineering, security-engineering
last-reviewed: 2026-09-05
review-cycle: 12 months
next-review: 2027-09-05
---

## Scope

ISO/IEC 42007 is being developed as a controls framework companion to ISO/IEC
42001:2023 (AI Management Systems). It defines a catalogue of AI-specific
control objectives and implementation guidance covering the AI system lifecycle,
data governance, model development, deployment, monitoring, and retirement.

This guide tracks the published draft clauses, the planned control taxonomy,
and how ORCHORDS profiles draft controls so audit and engineering decisions
stay current with the standard as it matures.

## Identifier Table

| Field | Value |
| --- | --- |
| Standard | ISO/IEC 42007 (committee draft) |
| Title | Information technology — Artificial intelligence — AI controls framework |
| Stage | DTR / DIS as of 2026 |
| Sponsor | ISO/IEC JTC 1/SC 42 / WG 1 |
| Companion | ISO/IEC 42001:2023, ISO/IEC 23894:2023, ISO/IEC 42005, ISO/IEC 42006 |
| Replaces | None — supplements ISO/IEC 42001 Annex A |

## Plan

While the standard finalises, ORCHORDS treats the working draft as the
reference taxonomy and proceeds as follows:

1. Adopt the draft control objectives as the canonical taxonomy inside the
   AIMS control library.
2. Maintain a mapping from each draft control to currently implemented
   controls (ISO/IEC 27001 Annex A, NIST SP 800-53 Rev 5, OWASP ML Top 10).
3. Tag controls with the AI lifecycle phase they apply to (design, data,
   model, deployment, monitoring, retirement).
4. Re-baseline the control library when ISO/IEC 42007 reaches IS status.

## Inputs

- Draft ISO/IEC 42007 control objectives and implementation guidance.
- Existing AIMS statement of applicability and supporting evidence.
- AI system inventory with lifecycle phase tagging.
- Mapping tables to ISO/IEC 27001 Annex A and NIST SP 800-53 Rev 5.

## ORCHORDS Profile Table

| ORCHORDS field | ORCHORDS value |
| --- | --- |
| Lifecycle phases | Design, Data, Model, Deploy, Operate, Retire |
| Control families | AI Governance, Data Quality, Model Robustness, Transparency, Human Oversight, Incident Management |
| Mapping baseline | ISO/IEC 27001:2022, NIST SP 800-53 Rev 5, OWASP ML Top 10 |
| Update cadence | On every committee draft and at IS publication |
| Compliance gate | Quarterly mapping review by AIMS owner |

## Implementation Notes

- ISO/IEC 42007 is the catalogue; ISO/IEC 42001 remains the management system.
  ORCHORDS keeps them clearly separated in the control library.
- Where ISO/IEC 42007 references emerging practices (for example, model
  cards, datasheets, AI red teaming), ORCHORDS captures the requirement at the
  control objective level and lets internal tooling implement the practice.
- Draft clauses often change classification; ORCHORDS tracks each control's
  stability status before treating it as a contractual requirement.

## Companion Documents

- ISO/IEC 42001:2023 Reference Card
- ISO/IEC 23894:2023 Reference Card
- ISO/IEC 42006:2023 Reference Card
- NIST AI 100-1 Reference Card
- OWASP Top 10 for LLM Applications Playbook Set
