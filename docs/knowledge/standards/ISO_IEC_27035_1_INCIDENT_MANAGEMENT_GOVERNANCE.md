---
title: "ISO/IEC 27035-1:2023 Incident Management Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "ISO/IEC 27035-1:2023; https://www.iso.org/standard/78973.html"
---

# ISO/IEC 27035-1:2023 Incident Management Governance

## Purpose

ISO/IEC 27035-1:2023, *Information technology — Information security incident management — Part 1: Principles and process*, defines the principles and process for managing information security incidents. The 2023 revision aligns with ISO/IEC 27001:2022 and reorganizes the incident-management lifecycle into plan and prepare, detection and reporting, assessment and decision, response, and lessons learnt. Profiles governing incident-management policy and procedure should reference ISO/IEC 27035-1:2023 explicitly and bind to ISO/IEC 27035-2 and 27035-3 for the operational extensions.

## Current context and source status

ISO/IEC 27035-1:2023 was published in February 2023 and supersedes ISO/IEC 27035-1:2016. The 2016 edition remains visible in older procurement language; profiles should be re-ratified against the 2023 edition rather than carried forward unchanged. ISO/IEC 27035-2 was revised in 2023 (response planning and operational guidance) and ISO/IEC 27035-3 (incident response exercises) was published in 2020 and remains the current edition as of September 2026.

## Governance workflow and controls

1. Plan and prepare: define incident-management policy, scope, roles, responsibilities, communication channels, escalation thresholds, and the relationship to the broader Information Security Management System (ISMS).
2. Detection and reporting: instrument detection, ingestion, and event triage so potential incidents are escalated into the incident-management process with the supporting evidence retained.
3. Assessment and decision: classify the incident by severity, scope, impact, and category; decide whether to trigger full incident response.
4. Response: contain, eradicate, recover, and communicate according to the documented plan; capture decisions and the evidence on which they were based.
5. Lessons learnt: post-incident review, root-cause analysis, corrective-action tracking, and update of plans and procedures.
6. Document deviations with the approver, scope, expiration, and compensating controls; do not allow undocumented deviations from the plan.
7. Treat ISO/IEC 27035 as one input alongside ISO/IEC 27001, NIST SP 800-61, and the organization's regulator-specific breach-notification obligations.

## Validation and evidence

- An incident-management policy aligned with ISO/IEC 27035-1:2023 with named roles, escalation thresholds, and communication channels.
- Records of detection, assessment, decision, response, and lessons learnt for representative incidents.
- Corrective-action tracking that shows how lessons learnt feed back into controls and plans.
- Periodic incident-management exercises (per ISO/IEC 27035-3 or NIST SP 800-84) with documented outcomes.
- Coordination procedures with legal, privacy, regulator, and public-relations teams.

Evidence that omits the assessment and decision records, the response evidence, or the lessons-learnt feedback loop does not establish ISO/IEC 27035-1 conformance.

## Failure correction

Common defects include incident-management policy that is not aligned with the ISMS scope, missing escalation thresholds, unclear ownership of the assessment and decision step, and lessons-learnt actions that are recorded but not tracked. Corrective actions include re-ratifying the policy against the current ISO/IEC 27001:2022 scope, defining quantitative or qualitative escalation thresholds, naming the decision authority, and tracking corrective actions in the same system as audit findings.

## Companion documents

- [ISO/IEC 27035-2:2023 Incident Response Version Transition Governance](ISO_IEC_27035_2_INCIDENT_RESPONSE_VERSION_TRANSITION_GOVERNANCE.md)
- [ISO/IEC 27035-3:2020 Incident Response Exercises Governance](ISO_IEC_27035_3_INCIDENT_RESPONSE_EXERCISES_GOVERNANCE.md)
- [ISO/IEC 27037:2012 Digital Evidence Version Transition Governance](ISO_IEC_27037_DIGITAL_EVIDENCE_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SP 800-61 Incident Handling Governance](NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md)
- [NIST SP 800-86 Forensic Techniques Governance](NIST_SP_800_86_FORENSIC_TECHNIQUES_GOVERNANCE.md)
- [Cybersecurity Incident Response Playbook](../playbooks/CYBERSECURITY_INCIDENT_RESPONSE.md)
