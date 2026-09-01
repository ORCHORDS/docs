# ISO/IEC 27018:2019 Version Transition Governance

## Purpose

This article describes how an organisation records, governs, and transitions between editions of **ISO/IEC 27018**, *Information technology — Security techniques — Code of practice for protection of personally identifiable information (PII) in public clouds acting as PII processors*. The current stable edition at the time of writing is ISO/IEC 27018:2019, the second edition, which supersedes ISO/IEC 27018:2014 and extends the code of practice to the updated control catalogue of ISO/IEC 27002:2013.

The article is governance guidance. It is not a substitute for the operative edition, an accredited certification body, or the organisation's privacy-management documentation.

## Scope

ISO/IEC 27018 is a code-of-practice standard that provides implementation guidance for the protection of personally identifiable information (PII) in public clouds acting as PII processors. The 2019 second edition is structured as an overlay on ISO/IEC 27002:2013 and ISO/IEC 27018 is commonly applied alongside ISO/IEC 27017:2015 (cloud code of practice) and ISO/IEC 27001 (information security management). It is intended primarily for cloud-service providers that act as PII processors, although some controls apply to the relationship between the provider and its PII controllers.

ISO/IEC 27018 does not on its own impose data-protection-law compliance, and a cloud-service provider that applies ISO/IEC 27018 should still satisfy the operative privacy regulation in each jurisdiction (for example, the EU GDPR, the UK GDPR, the Brazilian LGPD, the California CCPA/CPRA, or other national privacy regimes).

ISO/IEC 27018:2019 was published in January 2019. The publication date of the operative edition should be recorded alongside the edition reference in every artefact that cites the standard.

## Version governance workflow

### 1. Pin the operative edition and the date consulted

Every reference to ISO/IEC 27018 in policy, customer-facing material, audit reports, control matrices, or contractual clauses should record the exact edition (for example, ISO/IEC 27018:2019) and the publication date consulted. An unversioned reference loses meaning across the 2014 to 2019 transition because the control catalogue, the role assignments, and the consent-and-notice guidance changed.

### 2. Track ISO/IEC 27018 alongside ISO/IEC 27002, ISO/IEC 27017, and ISO/IEC 27001

ISO/IEC 27018:2019 is structured as an overlay on ISO/IEC 27002:2013. The 2022 re-edition of ISO/IEC 27002 does not automatically reissue ISO/IEC 27018. Governance should record the operative edition of ISO/IEC 27002 consulted alongside the ISO/IEC 27018 edition. Where ISO/IEC 27017:2015 is also applied, the editions of ISO/IEC 27017 and ISO/IEC 27018 should be recorded separately.

Where ISO/IEC 27001 is the certification basis, the ISMS edition should also be recorded separately. Cross-document evidence that mixes the editions of these standards is a frequent failure mode.

### 3. Distinguish PII-controller obligations from PII-processor obligations

ISO/IEC 27018:2019 is principally aimed at PII processors (typically cloud-service providers). It does not on its own establish the controller obligations defined by data-protection regulation. Governance documentation should record the role of the organisation (controller, processor, or both) and should not conflate controller obligations with processor obligations.

### 4. Manage consent and transparency claims carefully

ISO/IEC 27018:2019 provides guidance on consent, notification, and transparency in the public-cloud PII-processor context. A provider that applies ISO/IEC 27018 should not use the standard as the basis for claims about consent management, customer notification, or transparency that exceed the operative data-protection regulation. Conflating ISO/IEC 27018 application with legal consent under the applicable privacy regime is a frequent claim-related failure mode.

### 5. Distinguish ISO/IEC 27018 application from sectoral certification

Some sectors operate their own certification or attestation regimes that include ISO/IEC 27018 as a referenced standard. The sectoral regimes should be tracked independently of the ISO/IEC 27018 application. A claim that a cloud service is "certified against ISO/IEC 27018" should specify the certification body, the certification cycle, and the operative ISO/IEC 27001 and ISO/IEC 27002 editions consulted during the assessment.

### 6. Sequence certification transitions

ISO/IEC 27018 is typically applied as a code of practice and may be assessed as part of an ISO/IEC 27001 certification cycle. Certification bodies publish transition bulletins that describe transition timing, audit cycle alignment, and certificate re-issuance. The bulletin is the operative source for transition governance.

### 7. Preserve historical evidence under the edition it was created for

Internal audit reports, customer-facing attestations, and contractual clauses that were assessed against ISO/IEC 27018:2014 should remain labelled with the edition under which they were created. Reinterpreting legacy findings against ISO/IEC 27018:2019 without preserving the original edition breaks traceability.

### 8. Monitor amendments, corrigenda, and SC 27 output

ISO/IEC JTC 1/SC 27 is the joint technical committee sub-committee responsible for ISO/IEC 27018. Governance should subscribe to SC 27 publications and the ISO catalogue alerts for amendments, corrigenda, and interpretations. A change-log artefact should record the date of each change, the operative edition affected, and the affected clause numbers.

## Controls and evidence

Version-transition evidence typically includes:

- a dated edition register recording the ISO/IEC 27018 edition consulted for each artefact;
- paired edition registers recording the operative editions of ISO/IEC 27002, ISO/IEC 27017, and ISO/IEC 27001 consulted alongside ISO/IEC 27018;
- a privacy-policy and PII-processor documentation set that explicitly references the operative edition;
- a controller-processor allocation matrix stored with the edition reference under which it was created;
- customer-facing attestations stored with the edition reference under which they were issued;
- certification body transition bulletins, planned audit dates, and certificate re-issuance conditions;
- internal audit reports stored with the edition reference under which they were assessed;
- consent and transparency records stored with the edition reference under which they were created; and
- training and competency records showing staff were briefed on the operative edition and on the operative privacy regime.

## Validation

Validation that PII-processor controls continue to meet ISO/IEC 27018:2019 typically draws on:

- internal audits against the operative edition by auditors trained on the PII-processor context;
- external certification audits by an accredited certification body, where the organisation elects to pursue certification;
- customer reviews of the provider's PII-processor attestation under the operative privacy regulation;
- management review minutes that explicitly reference the operative edition and the transition status;
- corrective action closure and effectiveness review under the operative edition;
- certification body's public register of certified clients, which records the edition under which certification is held; and
- where applicable, sector-specific accreditation requirements (for example, healthcare, financial services, or public-sector cloud services).

## Failure correction

Common transition failures include:

- citing ISO/IEC 27018 without an edition in policy or customer-facing material;
- pairing ISO/IEC 27018:2019 with an ISO/IEC 27002 edition from a different edition cycle without documenting the discrepancy;
- conflating controller and processor obligations;
- making consent-management claims that rely on ISO/IEC 27018 application but exceed the operative data-protection regulation;
- failing to update the controller-processor allocation matrix when the service offering changes;
- treating documented information as merely a renaming exercise;
- losing historical evidence under the edition it was created for;
- mixing PII-in-public-cloud, cloud-code-of-practice, and information-security standards into a single document that fails to identify the operative edition of each standard; and
- ignoring amendments, corrigenda, or interpretations issued against ISO/IEC 27018.

A corrective action should document the edition under which the failure occurred, the operative edition that should have been used, the disposition of historical evidence, and the owner of the re-issued artefact.

## Limitations

ISO/IEC 27018:2019 is a code-of-practice standard, not a certification basis. Certification is typically assessed against ISO/IEC 27001. ISO/IEC 27018 does not on its own establish data-protection-law compliance, and it does not mandate specific technologies, deployment models, or service models.

ISO/IEC 27018:2019 is principally aimed at PII processors. Cloud-service providers that act as PII controllers for their own processing activities should apply the controller obligations of the operative privacy regulation separately.

## Canonical sources

- ISO — ISO/IEC 27018:2019, *Information technology — Security techniques — Code of practice for protection of personally identifiable information (PII) in public clouds acting as PII processors*: https://www.iso.org/standard/76559.html
- ISO/IEC JTC 1/SC 27 — Standing committee page on information security, cybersecurity and privacy protection: https://www.iso.org/committee/45306.html

## Scope note

This article describes version and reference governance for ISO/IEC 27018. It does not reproduce the standard, declare conformance with any data-protection law, or substitute for the operative edition, an accredited certification body, or the privacy-management documentation that defines the controller's and processor's obligations under the operative regulation.