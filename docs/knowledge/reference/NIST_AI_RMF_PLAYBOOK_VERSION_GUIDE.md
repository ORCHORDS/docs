---
title: "NIST AI RMF Playbook Version Guide"
standard: NIST AI RMF Playbook (cross-reference)
publisher: NIST
category: reference
subcategory: ai-governance
canonical_url: https://airc.nist.gov/Home
status: approved
classification: public
audience: ai-governance, model-development, security-engineering
last-reviewed: 2026-09-05
review-cycle: 12 months
next-review: 2027-09-05
---

## Scope

The NIST AI RMF Playbook is the practitioner-facing companion to NIST AI 100-1
(AI Risk Management Framework). It offers voluntary suggested actions,
templates, and reference architectures for each Govern/Map/Measure/Manage
function.

This guide tracks the Playbook's role in ORCHORDS AI operations and how it
links to other NIST AI resources.

## Identifier Table

| Field | Value |
| --- | --- |
| Document | NIST AI RMF Playbook (online) |
| Sponsor | NIST AI Safety Institute |
| Companion | NIST AI 100-1, NIST AI 100-2, NIST AI 600-1, NIST AI 700-series (companion profiles) |
| Status | Living document |

## Plan

1. Map each AI system under ORCHORDS AI operations to the four RMF functions
   using the Playbook's suggested actions as a checklist.
2. Use Playbook suggested actions to derive implementation evidence captured
   in AIMS audits.
3. Track each suggested action through the AIMS lifecycle: design, data,
   model, deploy, operate, retire.
4. Re-baseline suggested actions at Playbook updates and incorporate them
   into the next AI risk register review.

## Inputs

- AI system inventory and lifecycle stage.
- Playbook suggested actions per function.
- AIMS evidence repository.
- AI risk register and treatment records.

## ORCHORDS Profile Table

| Function | Suggested action theme | ORCHORDS profile evidence |
| --- | --- | --- |
| Govern | Policies, roles, escalation | AIMS policy register, RACI, escalation matrix |
| Map | Context, impacts, stakeholders | AI use case intake, FRIA output |
| Measure | Evaluation, testing, benchmarking | Model cards, eval results, red-team findings |
| Manage | Risk treatment, response, continuous monitoring | Incident records, control tests, ISCM evidence |

## Implementation Notes

- The Playbook is not a normative document; it informs but does not replace
  ORCHORDS-internal procedures.
- Each suggested action is treated as a control objective candidate. Where
  adopted, it is bound to the AIMS control library.
- The Playbook is updated more frequently than NIST AI 100-1; ORCHORDS keeps
  a dated reference of the version at the time of each audit.

## Companion Documents

- NIST AI 100-1 AI RMF Reference Card
- NIST AI 100-2 Adversarial ML Reference Card
- NIST AI 600-1 GenAI Profile Reference Card
- ISO/IEC 42001:2023 Reference Card
- ISO/IEC 23894:2023 Reference Card
- EU AI Act Reference Card
