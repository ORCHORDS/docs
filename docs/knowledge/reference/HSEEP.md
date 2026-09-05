---
title: "HSEEP — Homeland Security Exercise and Evaluation Program"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "HSEEP (FEMA, current published version); https://www.fema.gov/emergency-managers/national-preparedness/exercises/hseep"
---

# HSEEP — Homeland Security Exercise and Evaluation Program

## Scope

Reference card for HSEEP, the Homeland Security Exercise and Evaluation Program published by FEMA. HSEEP provides the methodology and terminology for designing, developing, conducting, and evaluating exercises across the prevention, protection, mitigation, response, and recovery mission areas. Profiles that govern an exercise programme for emergency management, business continuity, or incident response should reference HSEEP and bind it to ISO/IEC 27035-3, NIST SP 800-84, ISO 22398, and the NIST SP 800-61 incident-handling workflow.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | HSEEP (current published version, FEMA) |
| Status | Continuously maintained by FEMA |
| Companion artifacts | ISO/IEC 27035-3 (incident response exercises), ISO 22398 (exercises), NIST SP 800-84 (TT&E), NIST SP 800-61 (incident handling) |
| Source URL | https://www.fema.gov/emergency-managers/national-preparedness/exercises/hseep |

## Plan

1. Reference HSEEP by current version whenever a profile governs an exercise programme.
2. Adopt HSEEP exercise types: seminars, workshops, tabletop exercises, games, drills, functional exercises, and full-scale exercises.
3. Adopt HSEEP methodology: design and development (foundational documents, objectives, scenario, evaluation guides); conduct (controller, evaluator, simulator, player roles); evaluation (after-action report, improvement plan).
4. Adopt the HSEEP improvement-plan (IP) framework: corrective actions, owners, timelines, and tracking.
5. Bind to ISO/IEC 27035-3 for incident-response-specific exercise guidance.
6. Bind to NIST SP 800-84 for the IT-plan TT&E programme.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- HSEEP methodology documents.
- Internal exercise programme: schedule, scenarios, participants, evaluation guides, after-action reports.
- Improvement-plan tracking system.
- Risk-management framework (ISO 31000, NIST CSF) and the threat model.

## ORCHORDS Profile

ORCHORDS treats HSEEP as the canonical reference for the exercise methodology across prevention, protection, mitigation, response, and recovery. Profiles that reference exercises should cite HSEEP by version, identify the exercise types in scope, and bind to ISO/IEC 27035-3, NIST SP 800-84, and ISO 22398.

A profile that references "exercises" without binding to a recognized methodology is non-conformant.

## Implementation Notes

- HSEEP exercise types map to different learning objectives; tabletop exercises are not substitutes for full-scale exercises.
- Foundational documents (FEMA Threat and Hazard Identification and Risk Assessment, FEMA Core Capabilities, etc.) should be used as inputs to the exercise design.
- After-action reports and improvement plans are the primary evidence that the exercise programme is operating effectively.
- Improvement plans must be tracked to closure; exercises that produce no corrective-action tracking are non-conformant.
- HSEEP methodology can be applied to cybersecurity incidents, natural disasters, supply-chain events, and other scenarios.

## Companion Documents

- [ISO/IEC 27035-3:2020 Incident Response Exercises Governance](../standards/ISO_IEC_27035_3_INCIDENT_RESPONSE_EXERCISES_GOVERNANCE.md)
- [ISO 22398 Exercises](ISO_22398_EXERCISES.md)
- [NIST SP 800-84 Test, Training, and Exercise Program](NIST_SP_800_84_TEST_TRAINING_EXERCISE.md)
- ISO 22301 Business Continuity Management
- [Tabletop Exercise Response Playbook](../playbooks/TABLETOP_EXERCISE_RESPONSE.md)
