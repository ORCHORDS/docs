---
title: "NIST SP 800-84 Test, Training, and Exercise Program"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-84 (September 2006); https://csrc.nist.gov/publications/detail/sp/800-84/final"
---

# NIST SP 800-84 Test, Training, and Exercise Program

## Scope

Reference card for NIST Special Publication 800-84, *Guide to Test, Training, and Exercise Programs for IT Plans and Capabilities* (September 2006). The publication remains the current NIST reference for IT-plan test, training, and exercise (TT&E) program design and execution. Profiles that govern a TT&E programme should reference SP 800-84 and bind it to ISO/IEC 27035-3, HSEEP, ISO 22398, and the NIST SP 800-61 incident-handling workflow.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-84 (September 2006) |
| Status | Final; current edition (no successor revision as of September 2026) |
| Companion artifacts | ISO/IEC 27035-3 (incident response exercises), ISO 22398 (exercises), HSEEP, NIST SP 800-61 (incident handling), NIST SP 800-34 (contingency planning) |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-84/final |

## Plan

1. Reference SP 800-84 by version whenever a profile governs a TT&E programme for IT plans and capabilities.
2. Establish the TT&E programme: scope, objectives, frequency, types (tests, training, exercises), participants, success criteria, and link to the incident-management plan.
3. Test types: tabletop, walkthrough, simulation, full rehearsal, and parallel / partial cutover for contingency plans.
4. Training types: awareness, role-based, and competency assessment; track completion and the assessment outcome.
5. Exercise design: realistic, scoped, time-boxed, aligned to the highest-likelihood scenarios in the threat model.
6. Exercise evaluation: observer notes, participant feedback, success criteria scoring, deviation log, and findings.
7. Improvement: corrective actions, updates to plans and procedures, updates to the training programme, updates to the exercise scenario library.

## Inputs

- SP 800-84 normative sections: 3 (TT&E fundamentals), 4 (program design), 5 (program execution), 6 (program maintenance).
- ISO/IEC 27035-3 incident-response exercises and HSEEP exercise methodology.
- Internal IT plans (incident response, contingency, disaster recovery) and the scenarios that exercise each plan.
- Training material, completion records, and competency assessments.

## ORCHORDS Profile

ORCHORDS treats SP 800-84 as the canonical NIST reference for TT&E programmes. Profiles that reference IT-plan exercises should cite the standard by version, identify the exercise types in scope, and bind to ISO/IEC 27035-3, HSEEP, ISO 22398, and the NIST SP 800-61 incident-handling workflow.

A profile that references "exercises" without binding to a recognized methodology is non-conformant.

## Implementation Notes

- TT&E programme design should align the frequency with the risk profile and the regulatory expectations.
- Exercise types should match the learning objective; tabletop exercises are not substitutes for live rehearsals of contingency plans.
- Exercise evaluation must capture corrective actions; an exercise without corrective-action tracking is incomplete.
- Training cadence and content should be reviewed at least annually and updated when the IT plans change.
- Exercise scenario library should be aligned with the current threat model and updated after significant incidents.

## Companion Documents

- [ISO/IEC 27035-3:2020 Incident Response Exercises Governance](../standards/ISO_IEC_27035_3_INCIDENT_RESPONSE_EXERCISES_GOVERNANCE.md)
- [ISO/IEC 27035-1:2023 Incident Management Governance](../standards/ISO_IEC_27035_1_INCIDENT_MANAGEMENT_GOVERNANCE.md)
- [NIST SP 800-34 Contingency Planning](NIST_SP_800_34_CONTINGENCY_PLANNING.md)
- [HSEEP](HSEEP.md)
- [ISO 22398 Exercises](ISO_22398_EXERCISES.md)
- [Tabletop Exercise Response Playbook](../playbooks/TABLETOP_EXERCISE_RESPONSE.md)
