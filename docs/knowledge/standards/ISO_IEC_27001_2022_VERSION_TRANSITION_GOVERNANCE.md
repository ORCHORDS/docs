# ISO/IEC 27001:2022 Version Transition Governance

## Purpose

This article describes how an organization records, governs, and transitions between editions of **ISO/IEC 27001**, *Information security, cybersecurity and privacy protection — Information security management systems — Requirements*. The current stable edition at the time of writing is the third edition, ISO/IEC 27001:2022, which aligns the requirements clauses with ISO's Harmonized Structure (HLS) introduced in Annex SL and reorganises Annex A controls to a five-attributed taxonomy of organisational, people, physical, technological, and informational controls.

The article is governance guidance. It does not interpret individual ISO/IEC 27001 clauses, does not assign compliance outcomes, and does not replace the ISO catalogue, an accredited certification body, or the operative text of the ISMS standard itself.

## Scope

ISO/IEC 27001 is a management-system standard. It specifies the requirements for establishing, implementing, maintaining, and continually improving an Information Security Management System (ISMS) and for assessing and treating information-security risks. The 2022 edition supersedes the 2013 second edition; ISO confirmed the publication date of the third edition in October 2022, and national accreditation bodies and certification bodies have aligned their audit cycles to it.

Adjacent standards in the ISO/IEC 27000 family, including ISO/IEC 27000 (overview and vocabulary), ISO/IEC 27002 (controls guidance), ISO/IEC 27005 (risk management), ISO/IEC 27017 (cloud), ISO/IEC 27018 (PII in cloud), and ISO/IEC 27701 (privacy extension), are governed under their own edition cycles and should be tracked independently of ISO/IEC 27001 even where control numbering now aligns.

## Version governance workflow

### 1. Pin the operative edition

Every ISMS policy, statement of applicability, audit report, control mapping, and external claim must record the exact edition (for example, ISO/IEC 27001:2022) rather than the bare standard number. The edition and the date of the edition consulted should appear together with the audit or certification cycle under which it was used.

A control mapping that records "ISO/IEC 27001, Annex A.5.1" without an edition pin is ambiguous because the 2013 and 2022 editions use different annex control identifiers.

### 2. Capture transition delta explicitly

A transition project should record the changed, added, removed, merged, and renumbered Annex A controls between the previous and current edition. For the 2013 to 2022 transition, this includes the move from four control objectives to five attributes, the consolidation of 14 control categories into 4, the introduction of new themes such as threat intelligence and information security for use of cloud services, and the retirement of legacy controls that are now treated under ISO/IEC 27002 guidance.

The delta table should be versioned and dated, and it should be retrievable for the duration of any audit cycle that began under the prior edition.

### 3. Update the Statement of Applicability with edition discipline

The Statement of Applicability (SoA) is a normative requirement under ISO/IEC 27001:2022 Clause 6.1.3. The SoA must list each Annex A control considered, the justification for inclusion or exclusion, the implementation status, and the reference to the implementation guidance used. After a transition, the SoA must be re-issued under the new annex structure, and the prior SoA must be retained to interpret historical audit findings.

A change in annex structure does not by itself justify removing a control. Removal requires a justified exclusion that meets the standard's risk-treatment expectations.

### 4. Sequence independent accreditations

ISO/IEC 27001 certification cycles are typically three years with surveillance audits. Where an organization is mid-cycle, the certification body and the national accreditation body will define how the transition is sequenced against the certification validity. The ISMS team's role is to record the certification body's transition bulletin, the planned audit dates, and the conditions under which the certificate will be reissued under the new edition.

Transition windows are not uniform. Some accreditation bodies issue certificates with a limited transition period; others allow evidence assessed against the prior edition to be carried forward for a defined grace period. Governance must capture the operative accreditation rules, not generic guidance.

### 5. Cross-references to ISO/IEC 27002

ISO/IEC 27001:2022 Annex A now uses an attribute-based taxonomy that aligns with the attribute structure introduced in ISO/IEC 27002:2022. Where an organisation relies on ISO/IEC 27002 for implementation guidance, the ISMS should record the edition of ISO/IEC 27002 consulted alongside the edition of ISO/IEC 27001. A mixed reference such as "ISO/IEC 27001:2022 with ISO/IEC 27002:2013 controls" is acceptable only if the deliberate inconsistency is documented.

### 6. Monitor amendments and corrigenda

ISO management-system standards are typically amended rather than re-edited between major cycles. An organisation should subscribe to the ISO catalogue alert for the standard, monitor the ISMS user's national member body (for example BSI in the United Kingdom, ANSI in the United States, DIN in Germany, SAC in China, BIS in India), and track any amendments, corrigenda, and interpretation documents published by ISO TC 292 or ISO/IEC JTC 1/SC 27.

## Controls and evidence

Version-transition evidence typically includes:

- a dated edition register listing the exact ISO/IEC 27001 edition and publication date consulted;
- a transition delta between the previous and current editions, including changed, added, removed, and renumbered Annex A controls;
- a re-issued Statement of Applicability under the current annex taxonomy with versioned historical copies preserved;
- certification body transition bulletins, the planned audit dates, and the conditions for reissuing the certificate under the new edition;
- audit reports and findings stored with the edition reference under which they were assessed;
- mappings to ISO/IEC 27002 that record the edition of both standards;
- records of training and competency for staff on the new annex structure; and
- communication records showing internal and, where relevant, external stakeholders were informed of the edition change.

## Validation

Validation that the ISMS continues to meet ISO/IEC 27001:2022 requirements typically draws on:

- internal audits against the current edition, conducted with auditors trained on the new annex taxonomy;
- external audits by an accredited certification body operating under ISO/IEC 17021-1 and the applicable accreditation rules;
- management review minutes that explicitly reference the edition under review and the transition status;
- corrective actions tracked against the edition they were raised under;
- the certification body's public register of certified clients, which records the edition under which certification is held; and
- where applicable, accreditation-body oversight reports or transition-fairness decisions.

## Failure correction

Common transition failures include:

- using an unversioned "ISO 27001" label in evidence, mappings, or public claims;
- carrying forward the previous annex structure into a 2022 SoA without re-issuing the SoA;
- claiming compliance with the new edition before the certification body has reissued the certificate;
- mixing 2013 controls with 2022 annex numbering in mappings or customer-facing material;
- deleting Annex A controls that are not in the new taxonomy without applying the justified-exclusion discipline;
- failing to retain historical evidence under the edition it was created for; and
- ignoring dependent standards that have their own edition cycles, especially ISO/IEC 27002 and ISO/IEC 27005.

A corrective action should record the edition under which the failure occurred, the operative edition that should have been used, the disposition of the historical evidence, and the owner responsible for re-issuing the artefact.

## Limitations

ISO/IEC 27001:2022 is a management-system standard. It does not, by itself, mandate specific technical controls, and conformance with the standard does not equate to legal or regulatory compliance. Adjacent ISO/IEC 27000 family standards, ISO/IEC 27005 risk-management guidance, and industry frameworks such as SOC 2 or NIST SP 800-53 are governed independently.

ISO/IEC 27001:2022 does not include formal transition mechanisms defined in the standard itself. Transition periods, audit windows, and certification re-issuance are governed by certification bodies and accreditation bodies under ISO/IEC 17021-1 and ISO/IEC 17011 respectively, and the operative rules may differ between accreditation regions.

## Canonical sources

- ISO — ISO/IEC 27001:2022, *Information security, cybersecurity and privacy protection — Information security management systems — Requirements*: https://www.iso.org/standard/82875.html
- ISO/IEC JTC 1/SC 27 — Standing committee page on information security, cybersecurity and privacy protection: https://www.iso.org/committee/45306.html

## Scope note

This article describes version and reference governance for ISO/IEC 27001. It does not reproduce the standard, declare conformance, or substitute for the operative edition, an accredited certification body, or an ISMS-specific Statement of Applicability.