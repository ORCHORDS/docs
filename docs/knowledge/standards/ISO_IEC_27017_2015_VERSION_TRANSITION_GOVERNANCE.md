# ISO/IEC 27017:2015 Version Transition Governance

## Purpose

This article describes how an organisation records, governs, and transitions between editions of **ISO/IEC 27017**, *Information technology — Security techniques — Code of practice for information security controls based on ISO/IEC 27002 for cloud services*. The current stable edition at the time of writing is ISO/IEC 27017:2015, the first edition of the standard. ISO/IEC 27017 provides implementation guidance for cloud-service customers and cloud-service providers on the application of the controls enumerated in ISO/IEC 27002 and introduces additional cloud-relevant controls and implementation guidance.

The article is governance guidance. It is not a substitute for the operative edition, an accredited certification body, or the organisation's cloud-security documentation.

## Scope

ISO/IEC 27017 is a code-of-practice standard. It does not contain normative requirements but provides implementation guidance for the controls in ISO/IEC 27002 (now ISO/IEC 27002:2022) and additional cloud-specific controls. ISO/IEC 27017 is intended to be used alongside ISO/IEC 27002 and an ISMS implemented under ISO/IEC 27001.

ISO/IEC 27017 was published in 2015. The publication date of the operative edition should be recorded alongside the edition reference in every artefact that cites the standard. The standard should be tracked independently of ISO/IEC 27001 and ISO/IEC 27002 because each has its own edition cycle.

Cloud-service providers and cloud-service customers typically operate under contractual clauses (such as the ISO/IEC 27017 controls and ISO/IEC 27018 PII-in-public-clouds code of practice) that are added on top of a base ISMS. A claim that "the cloud service is ISO/IEC 27017 certified" is typically a cloud-service-customer statement that the provider has been certified against ISO/IEC 27017 as part of an ISO/IEC 27001 ISMS, although ISO/IEC 27017 may be applied as a code of practice without certification.

## Version governance workflow

### 1. Pin the operative edition and the date consulted

Every reference to ISO/IEC 27017 in policy, customer-facing material, audit reports, control matrices, or contractual clauses should record the exact edition (for example, ISO/IEC 27017:2015) and the publication date consulted. The ISO catalogue page records the publication date, abstract, and operative edition reference, and these fields are sufficient to reconstruct the edition consulted at the time a control mapping was made.

### 2. Track ISO/IEC 27017 alongside ISO/IEC 27002 and ISO/IEC 27001

ISO/IEC 27017:2015 is structured as an overlay on ISO/IEC 27002 (the 2013 edition was the contemporaneous ISO/IEC 27002 edition when ISO/IEC 27017:2015 was published). The 2022 re-edition of ISO/IEC 27002 does not automatically reissue ISO/IEC 27017. Governance should record the operative edition of ISO/IEC 27002 consulted alongside the ISO/IEC 27017 edition. A claim that "ISO/IEC 27017:2015 is implemented" should specify which ISO/IEC 27002 edition provides the underlying control catalogue.

Where ISO/IEC 27001 is the certification basis, the ISMS edition should also be recorded separately. Cross-document evidence that mixes the editions of the three standards is a frequent failure mode.

### 3. Distinguish customer controls from provider controls

ISO/IEC 27017:2015 distinguishes between controls applicable to cloud-service customers and controls applicable to cloud-service providers. Both roles share most controls, but several controls are specific to one role. Governance should record the role under which each control is being claimed.

A customer claim about a cloud-service provider should record the provider's published ISO/IEC 27017 attestation, the certification body that issued it, the certification cycle, and the operative ISO/IEC 27001 and ISO/IEC 27002 editions. Customer claims that rely on a provider's attestation should not overstate the scope of the attestation.

### 4. Manage the shared-responsibility model explicitly

ISO/IEC 27017 does not prescribe the shared-responsibility model between cloud-service customers and providers, but it expects each party to identify the controls for which they are responsible and the controls for which the other party is responsible. Governance documentation should record:

- the boundary of the customer's responsibilities and the provider's responsibilities;
- the contractual controls that allocate responsibility between the parties; and
- the change-management process used to update the shared-responsibility model when the service offering changes.

Conflating customer and provider responsibilities obscures accountability and weakens the ISMS.

### 5. Coordinate with ISO/IEC 27018 for PII in public clouds

Cloud-service providers that process personally identifiable information (PII) as processors are typically expected to apply ISO/IEC 27018:2019 in addition to ISO/IEC 27017:2015. The two standards share many controls but ISO/IEC 27018 adds PII-specific guidance. Governance should record the operative edition of each standard.

### 6. Sequence certification transitions

ISO/IEC 27017 is typically applied as a code of practice and may be assessed as part of an ISO/IEC 27001 certification cycle. Certification bodies publish transition bulletins that describe transition timing, audit cycle alignment, and certificate re-issuance. The bulletin is the operative source for transition governance.

### 7. Preserve historical evidence under the edition it was created for

Internal audit reports, customer-facing attestations, and contractual clauses that were assessed against ISO/IEC 27017:2015 should remain labelled with the edition under which they were created. Reinterpreting legacy findings against a later edition without preserving the original edition breaks traceability.

### 8. Monitor amendments, corrigenda, and SC 27 output

ISO/IEC JTC 1/SC 27 is the joint technical committee sub-committee responsible for ISO/IEC 27017. Governance should subscribe to SC 27 publications and the ISO catalogue alerts for amendments, corrigenda, and interpretations. A change-log artefact should record the date of each change, the operative edition affected, and the affected clause numbers.

## Controls and evidence

Version-transition evidence typically includes:

- a dated edition register recording the ISO/IEC 27017 edition consulted for each artefact;
- paired edition registers recording the operative editions of ISO/IEC 27002 and ISO/IEC 27001 consulted alongside ISO/IEC 27017;
- cloud-security policy and shared-responsibility documentation that explicitly references the operative edition;
- customer and provider control mappings stored with the edition reference under which they were created;
- certification body transition bulletins, planned audit dates, and certificate re-issuance conditions;
- internal audit reports stored with the edition reference under which they were assessed;
- customer-facing attestations stored with the edition reference under which they were issued; and
- training and competency records showing staff were briefed on the shared-responsibility model and on the operative edition.

## Validation

Validation that cloud-security controls continue to meet ISO/IEC 27017:2015 typically draws on:

- internal audits against the operative edition by auditors trained on the cloud-specific controls and the shared-responsibility model;
- external certification audits by an accredited certification body, where the organisation elects to pursue certification;
- customer-attestation reviews by cloud-service customers;
- management review minutes that explicitly reference the operative edition and the transition status;
- corrective action closure and effectiveness review under the operative edition;
- certification body's public register of certified clients, which records the edition under which certification is held; and
- where applicable, sector-specific accreditation requirements for cloud services (for example, healthcare, financial services, or public-sector cloud services).

## Failure correction

Common transition failures include:

- citing ISO/IEC 27017 without an edition in policy or customer-facing material;
- pairing ISO/IEC 27017:2015 with an ISO/IEC 27002 edition from a different edition cycle without documenting the discrepancy;
- conflating customer and provider controls without recording the role under which each control is claimed;
- making customer claims that overstate the scope of a provider's attestation;
- failing to update the shared-responsibility model when the service offering changes;
- treating documented information as merely a renaming exercise;
- losing historical evidence under the edition it was created for;
- mixing cloud-security, information-security, and PII-in-public-cloud standards into a single document that fails to identify the operative edition of each standard; and
- ignoring amendments, corrigenda, or interpretations issued against ISO/IEC 27017.

A corrective action should document the edition under which the failure occurred, the operative edition that should have been used, the disposition of historical evidence, and the owner of the re-issued artefact.

## Limitations

ISO/IEC 27017:2015 is a code-of-practice standard, not a certification basis. Certification is typically assessed against ISO/IEC 27001. ISO/IEC 27017 does not on its own define which controls apply to a given organisation; applicability is decided by the customer's or provider's risk assessment and recorded in the ISMS documentation.

ISO/IEC 27017 does not prescribe the shared-responsibility model between customers and providers. The standard does not mandate specific technologies, deployment models (public, private, hybrid, community), or service models (IaaS, PaaS, SaaS).

## Canonical sources

- ISO — ISO/IEC 27017:2015, *Information technology — Security techniques — Code of practice for information security controls based on ISO/IEC 27002 for cloud services*: https://www.iso.org/standard/43757.html
- ISO/IEC JTC 1/SC 27 — Standing committee page on information security, cybersecurity and privacy protection: https://www.iso.org/committee/45306.html

## Scope note

This article describes version and reference governance for ISO/IEC 27017. It does not reproduce the standard, declare conformance, or substitute for the operative edition, an accredited certification body, or the ISMS documentation that defines the customer's and provider's responsibilities.