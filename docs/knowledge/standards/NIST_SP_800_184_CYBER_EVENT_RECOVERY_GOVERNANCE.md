# NIST SP 800-184 — Cybersecurity Event Recovery Guide Governance

## 1. Scope

This card governs the adoption of NIST Special Publication 800-184, *Guide for Cybersecurity Event Recovery*, as the policy and procedure framework for recovering information systems, services, and data after a cybersecurity event. It applies to all production systems, supporting infrastructure, and third-party services that the organization depends on for the delivery of business-critical functions. The card establishes the recovery-planning, recovery-execution, and improvement obligations that Business Continuity, Security, and IT Operations teams must meet for every tier-1 and tier-2 service.

## 2. Normative references

- NIST SP 800-184 — *Guide for Cybersecurity Event Recovery*.
- NIST SP 800-61 Rev. 2 — *Computer Security Incident Handling Guide*.
- NIST SP 800-34 Rev. 1 — *Contingency Planning Guide for Federal Information Systems*.
- NIST SP 800-53 Rev. 5 — Contingency Planning (CP) control family.
- ISO/IEC 27035-1:2023 — *Information security incident management — Principles and processes*.
- ISO/IEC 27035-2:2023 — *Guidelines to plan and prepare for incident response*.
- ISO/IEC 27031:2011 — *Guidelines for ICT readiness for business continuity*.
- ISO/IEC 22301:2019 — Security and resilience — Business continuity management systems.

## 3. Terms and definitions

- **Cybersecurity Event** — any observable occurrence that compromises or attempts to compromise the confidentiality, integrity, or availability of an information system.
- **Recovery** — the process of restoring an information system and its data to a known-good state following a cybersecurity event.
- **Recovery Time Objective (RTO)** — the maximum acceptable duration between service disruption and restoration of service to a defined level.
- **Recovery Point Objective (RPO)** — the maximum acceptable data loss measured as the time elapsed since the last known-good backup.
- **Recovery Execution Phase** — the structured set of activities performed between incident containment and full restoration of normal operations.
- **Validation and Verification** — the post-recovery activities that confirm the restored system meets its security and operational baseline.
- **Lessons Learned** — the structured post-incident review that captures observations, root causes, and improvement actions.

## 4. Recovery planning and continuity

Recovery planning integrates cybersecurity-event recovery with business continuity and contingency planning so that recovery priorities reflect business impact.

- Each tier-1 and tier-2 service has a documented Cybersecurity Event Recovery Plan (CERP) that references its underlying contingency plan and is reviewed annually.
- The CERP identifies the system owner, the recovery team, the escalation paths, the dependencies, the prioritized recovery sequence, and the critical assets to be restored first.
- Recovery plans integrate with the Business Impact Analysis and the broader Business Continuity Management System to align RPO and RTO targets with the organization's risk appetite.
- Plans are stored in a controlled repository with offline copies, versioned history, and at-rest encryption; access is restricted to the named recovery team and Security Engineering.
- Recovery plans are exercised at least annually using tabletop, walkthrough, simulation, or full-interruption methods, with results retained as compliance evidence.
- The plan coordinates with NIST SP 800-61 incident-handling roles so that containment, eradication, and recovery teams operate from a shared understanding of priorities.

## 5. Recovery objectives (RPO/RTO)

Recovery objectives are explicit, measurable, and traceable to business impact.

- Every tier-1 service declares an RTO and an RPO that have been agreed by the business owner, Security, and IT Operations.
- Tier-1 RTO targets do not exceed four hours; tier-2 RTO targets do not exceed twenty-four hours. RPO targets do not exceed one hour for tier-1 and four hours for tier-2.
- Recovery objectives are reviewed at least annually, after any material change in service architecture, and following any recovery event that missed the declared target.
- Backup strategy is aligned to the declared RPO: daily full backups, continuous or near-continuous incremental replication, immutable storage for ransomware resistance, and quarterly restoration testing.
- Recovery objectives are published in the service catalogue and serve as input to internal and external Service Level Agreements.
- Where RPO or RTO targets cannot be met, a documented exception, compensating controls, and a Security Council waiver are required.

## 6. Recovery execution phases

Recovery execution follows the structured sequence defined by NIST SP 800-184.

- Pre-recovery: confirm containment per NIST SP 800-61, validate the integrity of backup data, and document the known-good baseline to be restored.
- Recovery initiation: activate the recovery team, declare the recovery state, notify the business owner and Security Steering Committee, and open the recovery log.
- Restoration: reimage, rebuild, or restore systems from trusted media; apply security patches; reinstate hardened configurations validated against the documented baseline.
- Validation and verification: run security scans, integrity checks, and functional smoke tests; confirm audit logging is operational and that monitoring is enabled before service is restored.
- Service restoration: bring the restored system into production behind a phased rollout; verify SLAs and dependencies before declaring normal service.
- Post-recovery: preserve forensic evidence per NIST SP 800-86, update the incident record, and hand the system back to steady-state operations.

## 7. Lessons learned and improvement

Every cybersecurity-event recovery closes with a formal lessons-learned review that converts observations into tracked improvement actions.

- A lessons-learned meeting is convened within ten business days of recovery completion for tier-1 events and within twenty business days for tier-2 events.
- The review captures timeline accuracy, decision quality, plan gaps, communication effectiveness, RPO/RTO performance, and customer impact.
- Improvement actions are recorded in the action-tracking system with an owner, a due date, a severity, and a verification step; status is reviewed monthly.
- Updated plan content, new controls, and refreshed training are propagated into the CERP, the CISO dashboard, and the security-awareness programme.
- Recovery metrics (RTO achieved, RPO achieved, recovery-event count, mean time to recover) are reported quarterly to executive leadership and aligned with ISO/IEC 27035 reporting cadence.
- This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
