---
title: "ISO 22301 Business Continuity Management"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "ISO 22301:2019; https://www.iso.org/standard/75106.html"
---

# ISO 22301 Business Continuity Management

## Scope

Reference card for ISO 22301:2019, *Security and resilience — Business continuity management systems — Requirements*. ISO 22301:2019 is the international standard for a Business Continuity Management System (BCMS). Profiles that govern business continuity should reference ISO 22301:2019 by version and bind it to NIST SP 800-34 (Contingency Planning), NIST SP 800-84 (TT&E), ISO/IEC 27031 (ICT readiness), ISO 22398 (exercises), HSEEP, and the ISO 22317 (business impact analysis).

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | ISO 22301:2019 |
| Status | Published (October 2019); current edition |
| Supersedes | ISO 22301:2012 |
| Companion artifacts | ISO 22317:2021 (BIA), ISO 22398:2013 (exercises), ISO/IEC 27031:2011 (ICT readiness), NIST SP 800-34, NIST SP 800-84 |
| Source URL | https://www.iso.org/standard/75106.html |

## Plan

1. Reference ISO 22301:2019 by version whenever a profile governs a BCMS.
2. Establish the BCMS scope: organizational units, products, services, and the dependencies.
3. Leadership: top-management commitment, policy, organizational roles, responsibilities, and authorities.
4. Planning: context analysis, business impact analysis (BIA) per ISO 22317, risk assessment, and business continuity strategy.
5. Support: resources, competence, awareness, communication, and documented information.
6. Operation: business continuity procedures, incident response, communication, and the BCMS plans.
7. Performance evaluation: monitoring, measurement, internal audit, and management review.
8. Improvement: nonconformity, corrective action, and continual improvement.

## Inputs

- ISO 22301:2019 normative clauses 4–10.
- ISO 22317:2021 BIA methodology.
- Internal BCMS scope, BIA, risk assessment, BC plans, and exercise records.

## ORCHORDS Profile

ORCHORDS treats ISO 22301:2019 as the canonical reference for BCMS. Profiles that reference business continuity should cite the version, identify the BCMS scope, and bind to ISO 22317, NIST SP 800-34, and NIST SP 800-84.

A profile that references "business continuity" without binding to a recognized framework is non-conformant.

## Implementation Notes

- ISO 22301:2019 reorganized the 2012 edition to align with the ISO management-system structure (Annex SL); profiles should reference the 2019 edition explicitly.
- BIA per ISO 22317 identifies the products and services, the activities that support them, the dependencies, the recovery time objectives (RTO), and the recovery point objectives (RPO).
- BC plans should be exercised at least annually and after significant changes; live rehearsals are required for high-criticality products and services.
- BC plans should be stored in a location accessible during the BC scenario (for example print copy, offline repository, or cloud storage with documented recovery).
- Management review should include the status of BC exercises, the corrective actions, and the changes to the BCMS scope.

## Companion Documents

- [NIST SP 800-34 Contingency Planning](NIST_SP_800_34_CONTINGENCY_PLANNING.md)
- [NIST SP 800-84 Test, Training, and Exercise Program](NIST_SP_800_84_TEST_TRAINING_EXERCISE.md)
- [HSEEP](HSEEP.md)
- [ISO 22398 Exercises](ISO_22398_EXERCISES.md)
- [Disaster Recovery and Failover Response Playbook](../playbooks/DISASTER_RECOVERY_FAILOVER_RESPONSE.md)
