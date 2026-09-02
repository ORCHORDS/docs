# NIST SP 800-66 HIPAA Security Rule Template Governance

## Purpose

NIST SP 800-66 Revision 2, *Implementing the HIPAA Security Rule: A Cybersecurity Resource Guide* (February 2024), maps the administrative, physical, and technical safeguards of the HIPAA Security Rule (45 CFR Part 164 Subpart C) to practical cybersecurity capabilities. The corresponding reusable template captures, for each safeguard section, the implementation status, evidence references, gaps, and residual-risk disposition so a covered entity or business associate can demonstrate Security Rule compliance without re-creating the mapping from scratch.

The template must remain generic: it MUST NOT embed the names of covered entities, business associates, workforce members, business associate agreements, or specific clinical systems.

## Scope

This template applies to HIPAA-regulated electronic protected health information (ePHI) under the Security Rule. It does not replace the Privacy Rule (45 CFR Part 164 Subpart E) documentation, the Breach Notification Rule (45 CFR §164.400-414), or state-level medical-privacy overlays. It does not address HITRUST CSF certification evidence, although HITRUST-authored control mappings may be referenced inside the evidence column.

## Workflow

1. Open the template and complete the header with the entity role (covered entity or business associate), the administrative unit owning the assessment, the assessment date, and the review cadence.
2. For each Security Rule safeguard (administrative, physical, technical), populate:
   - Reference citation to the specific 45 CFR §164.308/310/312 standard(s) and implementation specification(s) (required or addressable).
   - Implementation status: implemented, partially implemented, not implemented, or not applicable.
   - Evidence reference: policy and procedure identifier, system identifier, configuration baseline, or log source.
   - Gap description and remediation owner.
   - Residual-risk acceptance if addressable and not implemented.
3. Identify and document the contingency plan (§164.308(a)(7)) components: data backup, disaster recovery, emergency mode operations, testing and revision procedures, and applications and data criticality analysis.
4. Identify and document the evaluation (§164.308(a)(8)) procedure: periodic technical and non-technical evaluation cadence.
5. Identify and document the business associate contract (§164.308(b)) provisions: written contracts with required assurances and the breach notification cascade.
6. Save the completed template alongside the entity's compliance evidence repository, with access restricted to the security officer, privacy officer, and named reviewers.

## Controls and evidence

- Header records entity role, scope (systems, locations, data flows), assessment date, and reviewer.
- Per-safeguard rows record 45 CFR citation, status, evidence pointer, gap, owner, target date.
- Contingency plan section enumerates RTOs/RPOs by system, with last test date.
- Evaluation section enumerates the cadence and the prior evaluation's findings closure.
- Business associate section enumerates BAA inventory and last review date.
- Sign-off block records security officer, privacy officer, and management attestation.

## Validation

- Every addressable specification is either implemented or accompanied by a documented alternative measure and risk acceptance.
- Every "not implemented" entry has a target remediation date and owner.
- Contingency plan test records are referenced by date and outcome.
- BAA inventory is reconciled against the entity's vendor master list.
- Sign-off block has three named attestations (security, privacy, management).

## Failure correction

Common defects include treating addressable specifications as optional without documenting the alternative measure, missing contingency-plan test dates, failing to reconcile the BAA inventory against the vendor master, and accepting risk without naming the responsible officer. Corrective actions include restoring the addressable-implementation rationale, recording contingency tests, and adding BAA reconciliation as a recurring control activity.

## Limitations

- The template does not substitute for legal review of specific BAA terms.
- It does not address the HITRUST CSF assurance process or SOC 2 HIPAA mapping.
- It does not cover Privacy Rule documentation; a separate template is required for that purpose.
- It does not address the Security Rule's encryption-addressable transition to "decryption" addressable; entities should consult OCR guidance and current NIST cryptographic guidance.

## Scope note

This template is part of the **templates** leaf of the knowledge base. Sibling leaves cover: **security** (control baselines and overlays), **standards** (HIPAA-adjacent standards such as HITRUST and ISO 27799), **operations** (contingency exercise records and BAA inventories), and **business** (third-party-risk and BAA management). The template should be used together with those sibling-leaf articles where the topic overlaps.

## Canonical sources

- NIST SP 800-66 Rev 2, *Implementing the HIPAA Security Rule: A Cybersecurity Resource Guide* (NIST CSRC, February 2024): https://csrc.nist.gov/pubs/sp/800/66/r2/final
- 45 CFR Part 164 Subpart C, *HIPAA Security Rule* (U.S. Government Publishing Office): https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C
- HHS Office for Civil Rights, *HIPAA Security Rule Guidance*: https://www.hhs.gov/hipaa/for-professionals/security/

Sources were verified on September 1, 2026.
