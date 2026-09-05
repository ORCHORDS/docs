---
title: "NIST AI RMF — Map, Measure, Manage Functions Version Guide"
standard: NIST AI 100-1 — Map / Measure / Manage
publisher: NIST
category: reference
subcategory: ai-governance
canonical_url: https://www.nist.gov/itl/ai-risk-management-framework
status: approved
classification: public
audience: ai-governance, model-development, operations, security-engineering
last-reviewed: 2026-09-05
review-cycle: 12 months
next-review: 2027-09-05
---

## Scope

This guide covers the three execution functions of the AI RMF that sit on top
of Govern: Map (frame risks), Measure (analyse and benchmark), and Manage
(treat, accept, communicate). The three are tightly coupled; this card records
the structure of each so ORCHORDS AI operations can assemble evidence that
satellites within ISO/IEC 42001:2023 and the EU AI Act.

## Identifier Table

| Field | Value |
| --- | --- |
| Document | NIST AI 100-1 |
| Functions | Map, Measure, Manage |
| Subcategories | MAP 1.1 – 5.2, MEASURE 1.1 – 4.3, MANAGE 1.1 – 5.1 |
| Companion | NIST AI RMF Playbook, NIST AI 100-2, NIST AI 600-1 |

## Plan

1. Map each AI system to its operational context, stakeholders, and impacts
   in line with MAP subcategories.
2. Measure trustworthiness characteristics (valid, reliable, safe, secure,
   resilient, accountable, transparent, explainable, privacy-enhanced,
   fair) using documented methods and metrics.
3. Manage AI risks by prioritising, treating, accepting, transferring, or
   avoiding, with documented decisions and ongoing monitoring.
4. Embed continuous feedback: Measure informs Manage, Manage updates the
   risk register, Map is refreshed when context shifts.

## Inputs

- AI system inventory and lifecycle data.
- Trustworthiness evaluation metrics and benchmark results.
- AI risk register and treatment plans.
- Incident records from monitoring and post-market surveillance.

## ORCHORDS Profile Table

| Function | Key subcategories | ORCHORDS profile |
| --- | --- | --- |
| Map | MAP 1 (context), MAP 2 (categorisation), MAP 3 (impacts), MAP 4 (risks), MAP 5 (stakeholders) | Quarterly context review per AI system |
| Measure | MEASURE 1 (approaches), MEASURE 2 (rooted in evaluation), MEASURE 3 (human-AI configuration), MEASURE 4 (tracking) | Eval suite per trustworthiness characteristic |
| Manage | MANAGE 1 (prioritisation), MANAGE 2 (treatment), MANAGE 3 (documentation), MANAGE 4 (operationalisation), MANAGE 5 (communication) | Risk treatment plans with owners |

## Implementation Notes

- Each function has pre-conditions from Govern; ORCHORDS refuses to enter
  Map without an active Govern profile and an AI owner.
- MEASURE 4 (tracking) feeds the ISCM cadence; AI systems follow the same
  monitoring SLAs as critical production systems.
- MANAGE 5 outputs include communications to internal stakeholders and,
  where required by Article 73 EU AI Act, external incident reports.

## Companion Documents

- NIST AI 100-1 AI RMF Reference Card
- NIST AI RMF Playbook Reference Card
- NIST AI 100-2 Adversarial ML Reference Card
- NIST AI 600-1 GenAI Profile Reference Card
- ISO/IEC 23894:2023 Reference Card
- ISO/IEC 42001:2023 Reference Card
- EU AI Act Reference Card
