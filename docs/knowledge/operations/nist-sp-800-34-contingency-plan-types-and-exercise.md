# NIST SP 800-34 Contingency Plan Types and Exercise

## Purpose

NIST SP 800-34 Rev. 1 is the principal U.S. federal guidance on information system contingency planning. It sets a three-tier model: the Information System Contingency Plan (ISCP), the Disaster Recovery Plan (DRP), and the Business Continuity Plan (BCP). Each tier addresses a different temporal and organizational horizon. This article summarizes the three plans and the exercise program around them, so that engineering teams can align operational continuity work with a stable federal reference.

## Three plan types

**Information System Contingency Plan (ISCP)** — a procedure that prepares a specific system for operations following a disruption. It defines the system, the responsible personnel, the recovery objectives, the resources, the procedures, and the validation schedule. The ISCP is system-bound, and it is the most operational of the three plans.

**Disaster Recovery Plan (DRP)** — the information-system and technology-focused subset of recovery. The DRP focuses on restoring damaged systems, infrastructure, data, and applications to normal operation. Where the ISCP identifies what to do, the DRP identifies how to do it at the infrastructure and platform level.

**Business Continuity Plan (BCP)** — the organizational plan for continuing mission-essential functions while systems are recovered. BCPs address the people, processes, facilities, and external dependencies that the ISCP and DRP do not by themselves cover. The BCP is the bridge from the technology response to ongoing business operation.

All three plans are required where applicable. A single document may combine elements of all three, but the responsibilities, audiences, and exercise cadences differ, and the distinctions are useful at audit time even when they are not visible in the document structure.

## Plan hierarchy in practice

NIST treats the BCP, BCP/ISCP, and DRP as a hierarchy:

- BCP defines mission-essential functions and order of restoration at the business level;
- ISCP defines system-level recovery objectives, responsibilities, and immediate steps;
- DRP defines the technical recovery of platforms, applications, and data.

A contingency program that covers only the ISCP and skips the BCP will have a gap when business-level decisions must be made during a real event; one that covers only the BCP and skips the ISCP will not produce a usable, tested procedure at the system level. Both extremes should be reviewed during plan maintenance.

## Workflow for maintaining plans

1. Identify mission-essential functions and the systems that support them.
2. Categorize the systems against the relevant impact level using FIPS 199.
3. Define recovery objectives (RTO, RPO, minimum service level) for each system.
4. Assign roles and responsibilities for plan activation, including decision authorities.
5. Document technical and procedural steps required to meet the recovery objectives.
6. Define communication rules, escalation thresholds, and external coordination needs.
7. Test the plans and record results, failures, and corrective action.
8. Review plans after material system, organizational, or environmental change.

Maintenance is continuous, not episodic. The most common cause of plan failure in real events is that the people, contacts, or recovery steps in the plan no longer reflect the current state.

## Exercise types

NIST SP 800-34 defines a graduated set of exercise types, ordered from least to most disruptive:

- **Tabletop exercise** — facilitated discussion of a scenario to validate understanding of roles, processes, and decision flow.
- **Walkthrough** — step-by-step rehearsal with the actual plan document and the actual participants, performed at normal pace.
- **Simulation** — execution of the plan under a constructed but contained scenario; systems may be partially involved.
- **Parallel test** — operational test of a recovery environment without affecting production.
- **Full interruption test** — controlled activation of recovery procedures against production; the highest-trust exercise.

Lower-intensity exercises must occur more often; full-interruption tests are appropriate only for high-criticality systems and require explicit authorization because they create real risk during the exercise itself.

## Validation and evidence

Retain the most recent ISCP, DRP, and BCP for each system in scope, the recovery objectives with rationale, the role and roster data, the call tree and communications plan, the most recent exercise plan and exercise report for each exercise type performed, the corrective action tracker, plan-review minutes, and any data on real events the plans have supported. Reviewers should be able to reconcile the recovery objectives against the system categorization and the exercise results.

## Failure modes

Common failures include plans that document a recovery that the platform cannot actually perform, plans that have not been exercised at the appropriate level, contact lists without ownership or that point to inactive employees, recovery objectives that are assumed rather than derived from the impact analysis, and exercises that always pass because the scenario is too generous.

## Canonical sources

- NIST SP 800-34 Rev. 1, Contingency Planning Guide for Federal Information Systems: https://csrc.nist.gov/pubs/sp/800/34/r1/final
- FIPS 199, Standards for Security Categorization of Federal Information and Information Systems: https://csrc.nist.gov/pubs/fips/199/final
- NIST SP 800-61 Rev. 2 (history of incident handling responses relevant to continuity activation): https://csrc.nist.gov/pubs/sp/800/61/r2/final

## Scope note

This article summarizes contingency plan types and exercise design as references; it does not replace the current NIST guidance or supersede sector- or jurisdiction-specific continuity requirements such as those in ISO 22301, PCI DSS, or HIPAA contingency planning regulation.
