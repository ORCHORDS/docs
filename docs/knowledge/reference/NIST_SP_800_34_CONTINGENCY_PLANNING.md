---
title: "NIST SP 800-34 Contingency Planning"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-34 Rev. 1 (May 2010, includes updates); https://csrc.nist.gov/publications/detail/sp/800-34/rev-1/final"
---

# NIST SP 800-34 Contingency Planning

## Scope

Reference card for NIST Special Publication 800-34 Revision 1, *Guide for Conducting Contingency-Planning Exercises* and *Contingency Planning Guide for Federal Information Systems* (May 2010, with subsequent updates). The publication remains the canonical NIST reference for IT contingency planning. Profiles that govern contingency planning should reference SP 800-34 Rev. 1 and bind it to ISO 22301 (BCM), ISO/IEC 27031, NIST SP 800-84 (TT&E), and the FEMA / HSEEP exercise methodology.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-34 Rev. 1 (May 2010, with updates) |
| Status | Final; current edition (Rev. 2 in draft as of September 2026) |
| Companion artifacts | NIST SP 800-84 (TT&E), NIST SP 800-37 RMF, NIST SP 800-61 incident handling, ISO 22301, ISO/IEC 27031 |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-34/rev-1/final |

## Plan

1. Reference SP 800-34 Rev. 1 by version whenever a profile governs IT contingency planning.
2. Establish the contingency-planning policy: scope, objectives, roles, responsibilities, and the relationship to the broader business-continuity framework (ISO 22301).
3. Conduct a business-impact analysis (BIA) per SP 800-34 §3: identify critical IT resources, recovery time objectives (RTO), recovery point objectives (RPO), and the resource requirements.
4. Develop the contingency plan per SP 800-34 §4: preventive controls, recovery strategies, and the contingency plan contents.
5. Test, train, and exercise per SP 800-34 §5 and NIST SP 800-84.
6. Maintain the contingency plan per SP 800-34 §6: review, update, and change management.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- SP 800-34 Rev. 1 normative sections: 3 (BIA), 4 (contingency planning), 5 (testing, training, exercises), 6 (maintenance).
- ISO 22301 (BCM), ISO/IEC 27031 (ICT readiness for business continuity), NIST SP 800-84 (TT&E).
- Internal BIA, contingency plans, recovery strategies, and exercise records.

## ORCHORDS Profile

ORCHORDS treats SP 800-34 Rev. 1 as the canonical NIST reference for IT contingency planning. Profiles that reference contingency planning should cite the standard by version, identify the planning elements in scope, and bind to ISO 22301 and NIST SP 800-84.

A profile that references "contingency planning" without binding to a recognized framework is non-conformant.

## Implementation Notes

- RTO and RPO should be expressed at the system level, not at the application level alone; dependencies and infrastructure recovery time should be considered.
- Recovery strategies (cold, warm, hot, active-active) should be matched to the RTO/RPO and the cost envelope.
- The contingency plan should be exercised at least annually and after significant changes; live rehearsals (not just tabletop) are required for high-criticality systems.
- The contingency plan should be stored in a location accessible during the contingency (for example print copy, offline repository).
- BIA should be reviewed annually or when significant changes occur.

## Companion Documents

- [ISO 22301 Business Continuity Management](ISO_22301_BUSINESS_CONTINUITY_MANAGEMENT.md)
- [NIST SP 800-84 Test, Training, and Exercise Program](NIST_SP_800_84_TEST_TRAINING_EXERCISE.md)
- [Disaster Recovery and Failover Response Playbook](../playbooks/DISASTER_RECOVERY_FAILOVER_RESPONSE.md)
- [NIST SP 800-61 Incident Handling Governance](../standards/NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md)
