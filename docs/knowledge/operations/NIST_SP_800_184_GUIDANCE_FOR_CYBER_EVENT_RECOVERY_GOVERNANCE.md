# NIST SP 800-184 Guidance for Cyber Event Recovery Governance

## Purpose

NIST SP 800-184, "Guide for Cybersecurity Event Recovery," provides guidance on planning, executing, and validating the recovery from cybersecurity events (incidents that have compromised system integrity, confidentiality, or availability). The publication supplements SP 800-61 r3 with detailed guidance on recovery, including the recovery plan, the recovery capabilities, the execution, and the recovery validation. This article governs the application of SP 800-184 so the organization can recover from cybersecurity events with documented discipline.

## Scope

The publication applies to any organization that needs to recover from cybersecurity events. Within this knowledge base, the article covers the recovery process (plan, capabilities, execution, validation), the integration with the broader incident response and continuity processes, the documentation of recovery decisions, and the recovery exercises. It does not cover business continuity management generally (readers should consult ISO 22301 and NIST SP 800-34 for that); SP 800-184 focuses on the cybersecurity event recovery aspects.

## Workflow

1. Develop the recovery plan:
   - Define the recovery scope: which systems, which data, which services are in scope.
   - Define the recovery objectives: Recovery Time Objective (RTO), Recovery Point Objective (RPO), and the recovery sequence.
   - Define the recovery team, roles, and responsibilities.
   - Define the communication plan: internal, customers, partners, regulators.
   - Define the criteria for declaring a recovery event and ending the recovery.
2. Build the recovery capabilities: backups, clean environments for restoration, alternative operating locations, and the trained team.
3. Execute the recovery when a cybersecurity event requires it. Document each step with timestamps and decisions.
4. Validate the recovery: confirm systems are restored to expected state, monitor for re-emergence of the threat, and confirm business operations resume.
5. Conduct a post-recovery review: document the lessons learned and apply them to the plan.
6. Exercise the recovery plan on a planned cadence to confirm its operational viability.

## Controls and evidence

Recovery evidence includes the recovery plan, the recovery capability records (backups, environments, locations), the recovery execution records, the validation records, the post-recovery review minutes, and the exercise records. Each recovery event should be traceable from declaration through validation.

## Validation

Validation should confirm the recovery plan is current, the capabilities are operational, the team is trained, the exercises have been performed and produced improvements, and the recovery objectives (RTO, RPO) are achievable. Recovery exercises provide the strongest evidence of operational capability.

## Failure correction

Common failure modes: the recovery plan is written but the capabilities are not exercised (correct: schedule and perform recovery exercises); backups are not tested for restoration (correct: test backup restoration as part of the exercise); RTO and RPO are aspirational (correct: validate them through exercise); the recovery team is not trained (correct: train the team on the plan and the tools); the plan is not updated after incidents (correct: review and update after each recovery event).

## Limitations

NIST SP 800-184 provides guidance; it does not prescribe specific recovery tools or vendor products. The publication does not guarantee recovery outcomes; it ensures the recovery is systematic and exercised. Recovery for highly sophisticated attacks (where the attacker has deep, persistent access) requires additional capabilities beyond what the publication describes.

## Scope note

This article summarizes project-neutral operations use of NIST SP 800-184. It does not assert any specific organization's recovery conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-184 — Guide for Cybersecurity Event Recovery: https://csrc.nist.gov/publications/detail/sp/800-184/final
- NIST SP 800-34 r1 — Contingency Planning Guide for Federal Information Systems: https://csrc.nist.gov/publications/detail/sp/800-34/rev-1/final
- ISO 22301:2019 — Security and resilience — Business continuity management systems — Requirements: https://www.iso.org/standard/75106.html