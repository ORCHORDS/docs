---
title: "NIST SP 800-61 Incident Handling Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-61 Rev. 2 (April 2018); https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final"
---

# NIST SP 800-61 Incident Handling Governance

## Purpose

NIST Special Publication 800-61 Revision 2, *Computer Security Incident Handling Guide* (April 2018), defines the incident-handling lifecycle, the roles and functions of a Computer Security Incident Response Team (CSIRT), and recommended policies and procedures. Profiles that govern incident response should reference SP 800-61 Rev. 2 explicitly and bind it to ISO/IEC 27035, MITRE ATT&CK, and the organization's regulator-specific breach-notification obligations.

## Current context and source status

SP 800-61 Rev. 2 was published in April 2018 and supersedes Rev. 1 (March 2008). As of September 2026, Rev. 3 is in active draft but not yet published. Profiles should reference the current Rev. 2 by version and track the draft for revision when Rev. 3 is published. The 2018 revision reorganized the lifecycle into preparation; detection and analysis; containment, eradication, and recovery; and post-incident activity.

## Governance workflow and controls

1. Preparation: incident-handling policy, communication plan, contact list, hardware and software resources, training, and the relationship to the broader Information Security Management System.
2. Detection and analysis: detection sources, signature and anomaly analysis, correlation, scoping, and severity assignment.
3. Containment, eradication, and recovery: short-term and long-term containment, eradication of attacker artefacts, system recovery, and verification.
4. Post-incident activity: lessons-learnt review, root-cause analysis, corrective actions, and policy updates.
5. Maintain CSIRT role definitions: team members, escalation authority, communications lead, technical lead, and legal liaison.
6. Coordinate with law enforcement, regulator, and external stakeholders per the organization's regulatory profile.
7. Apply the SP 800-86 forensic-process guidance inside the containment and eradication stages when digital evidence is involved.

## Validation and evidence

- Incident-handling policy and supporting procedures aligned with SP 800-61 Rev. 2.
- CSIRT contact list, on-call rotation, and escalation matrix.
- Incident records spanning preparation through post-incident activity for representative events.
- Lessons-learnt review notes and corrective-action tracking.
- Coordination procedures with legal, regulator, and external communications.

Evidence that omits the lessons-learnt records, the corrective-action tracking, or the coordination procedures does not establish SP 800-61 Rev. 2 conformance.

## Failure correction

Common defects include missing escalation thresholds, ad-hoc containment decisions without evidence retention, and lessons-learnt meetings without corrective-action tracking. Corrective actions include defining quantitative escalation thresholds, integrating evidence retention into the containment playbook, and binding corrective-action tracking to the same workflow as audit findings.

## Companion documents

- [ISO/IEC 27035-1:2023 Incident Management Governance](ISO_IEC_27035_1_INCIDENT_MANAGEMENT_GOVERNANCE.md)
- [NIST SP 800-86 Forensic Techniques Governance](NIST_SP_800_86_FORENSIC_TECHNIQUES_GOVERNANCE.md)
- [NIST SP 800-84 Test, Training, and Exercise Program](../reference/NIST_SP_800_84_TEST_TRAINING_EXERCISE.md)
- [Cybersecurity Incident Response Playbook](../playbooks/CYBERSECURITY_INCIDENT_RESPONSE.md)
- [Incident Timeline Reconstruction Playbook](../playbooks/INCIDENT_TIMELINE_RECONSTRUCTION.md)
- MITRE ATT&CK Version Guide
