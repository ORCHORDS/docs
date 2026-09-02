# NIST SP 800-171 Rev 3 CUI Protection Governance

## Purpose

Govern the application of NIST SP 800-171 Rev 3 (Protecting Controlled Unclassified Information in Nonfederal Systems and Organizations, May 2024) so that controlled unclassified information (CUI) held in nonfederal systems receives the required protection: the 32 security requirements organized by the Rev 3 control families, with assessment readiness against SP 800-171A.

## Scope

Applies to every nonfederal system the studio operates that stores or processes CUI under a contract or agreement. Covers requirement implementation, system scope determination, and assessment evidence. Does not cover federal systems (SP 800-53 governs those) or the CMMC assessment regime itself.

## Workflow

1. Determine CUI scope precisely: which contract clauses obligate protection, which information is registered as CUI, and which systems actually store or process it — scope discipline matters because every requirement applies to the covered system set.
2. Map each of the 32 Rev 3 requirements to implementation evidence: policy, configuration, tooling output, or records — using the Rev 3 organization (access control, awareness and training, audit and accountability, configuration management, identification and authentication, incident response, maintenance, media protection, personnel security, physical protection, risk assessment, security assessment, system and services acquisition, system and communications protection, system integrity).
3. Implement SP 800-53-derived controls as Rev 3 directs: Rev 3 aligns each requirement to its SP 800-53 counterpart, so control implementations can share evidence with the 800-53 program where one exists.
4. Trace every requirement to an assessment objective: SP 800-171A defines the assessment objectives; evidence organized against objectives survives assessment, evidence organized by narrative does not.
5. Maintain the System Security Plan (SSP): Rev 3 requires documenting implementation per requirement; the SSP is the index connecting requirements, systems, and evidence.
6. Manage flows: CUI leaving the covered environment (subcontractors, cloud services) requires flow documentation and protection obligations passed downstream.
7. Assess on cadence: periodic self-assessment against 800-171A objectives, with gaps entered into a POA&M with owners and dates.

## Controls and evidence

- CUI scope determination record with contract citations.
- Requirements-to-evidence matrix organized by assessment objective.
- SSP maintained per Rev 3 documentation requirements.
- Flow documentation for CUI leaving the environment.
- Self-assessment results with POA&M entries.

## Validation

- Sample five requirements and confirm each has current evidence that satisfies its 800-171A objectives.
- Confirm the SSP reflects the actual system set, not a historical one.
- Confirm open POA&M items have owners and dates within policy windows.

## Failure correction

- **Requirement without current evidence** → implement or document compensating measures; evidence gaps found at assessment become findings with remediation deadlines.
- **Scope drift (new CUI outside covered systems)** → extend the covered set or move the processing into it; CUI processed on uncovered systems is a reportable breach of contract terms.
- **POA&M items overdue** → escalate per policy; persistent overdue items indicate under-resourcing that management must resolve, not absorb.

## Limitations

- SP 800-171 protects CUI in nonfederal systems only; federal systems use SP 800-53 baselines.
- The CMMC assessment regime layers its own processes on the same requirements; compliance with the requirements does not automatically satisfy CMMC assessment procedures.
- Rev 3 (May 2024) substantially reorganized the requirements from Rev 2; mappings and assessments against Rev 2 structures are obsolete.

## Scope note

This article is part of the security leaf. Cross-reference: `SYSTEM_PLAN_SECURITY_PRIVACY_C_SCRM_COORDINATION.md`, `NIST_SP_800_53_REV5_CONTROL_TEMPLATES_GOVERNANCE.md` (templates leaf), and `NIST_SP_800_171A_ASSESSMENT_OBJECTIVES_GOVERNANCE.md` sibling guidance.

## Canonical sources

- NIST SP 800-171 Rev 3 — Protecting Controlled Unclassified Information in Nonfederal Systems and Organizations (May 2024): https://csrc.nist.gov/pubs/sp/800/171/r3/final
- NIST SP 800-171A Rev 3 — Assessing Security Requirements for CUI: https://csrc.nist.gov/pubs/sp/800/171a/r3/final
- NIST SP 800-53 Rev 5 — Security and Privacy Controls: https://csrc.nist.gov/pubs/sp/800/53/rev-5/final
- NARA — CUI Registry: https://www.archives.gov/cui
- DoD CMMC — Cybersecurity Maturity Model Certification: https://dodcio.defense.gov/cmmc/
