# IEC 62443-2-1 Version Transition Governance

## Purpose

This article describes how an organisation records, governs, and transitions between editions of **IEC 62443-2-1**, *Industrial communication networks — Network and system security — Part 2-1: Establishing an industrial automation and control system security program*. The current stable edition at the time of writing is IEC 62443-2-1:2010, the first edition, published under the joint IEC/TC 65 and ISA 99 programme that defines the international 62443 series for Industrial Automation and Control Systems (IACS) security.

The article is governance guidance. It is not a substitute for the operative edition, an accredited certification body, or the organisation's industrial-cybersecurity programme documentation.

## Scope

IEC 62443-2-1 specifies the elements necessary to establish an industrial automation and control system (IACS) security programme and the requirements for the associated security-management system. The standard was jointly developed by IEC TC 65 (Industrial-process measurement, control and automation) Working Group 10 and the ISA 99 committee. In North America, the standard is also adopted as ANSI/ISA-62443-2-1.

The 2010 first edition has remained the operative edition at the time of writing, although amendments, corrigenda, and interpretations may be published between editions, and a second edition may be in development under IEC TC 65/WG 10. Governance should record the operative edition reference, monitor the IEC catalogue for changes, and plan for transition windows when a new edition is published.

The standard is one of the 62443 series, which covers general concepts (IEC 62443-1-1), policies and procedures (IEC 62443-2-1, IEC 62443-2-4), system security requirements and levels (IEC 62443-3-1, IEC 62443-3-2, IEC 62443-3-3), and component requirements (IEC 62443-4-1, IEC 62443-4-2). Each part has its own edition cycle and should be tracked independently.

## Version governance workflow

### 1. Pin the operative edition and the date consulted

Every reference to IEC 62443-2-1 in policy, programme documentation, audit reports, certification claims, or customer-facing material should record the exact edition (for example, IEC 62443-2-1:2010) and the publication date consulted. An unversioned reference loses meaning across any future re-edition because the security-programme requirements, security-level definitions, and the lifecycle model may change.

### 2. Track the 62443 series as a family

IEC 62443-2-1 is one part of the 62443 series. Governance should record the operative edition of each part consulted alongside IEC 62443-2-1, including:

- IEC 62443-1-1 (concepts and models);
- IEC 62443-2-1 (security programme establishment);
- IEC 62443-2-3 (patch management in the IACS environment);
- IEC 62443-2-4 (service-provider security);
- IEC 62443-3-1 (security technology requirements);
- IEC 62443-3-2 (security risk assessment and system design);
- IEC 62443-3-3 (system security requirements and security levels);
- IEC 62443-4-1 (secure product development lifecycle requirements);
- IEC 62443-4-2 (component security requirements); and
- ISO/IEC 62443 (cross-series common frameworks, where jointly maintained).

A claim that "the IACS complies with IEC 62443" should specify the part, the edition of each part consulted, and the security level targeted under IEC 62443-3-3.

### 3. Distinguish security levels from compliance claims

IEC 62443-3-3 defines four Security Levels (SL 1 to SL 4) that correspond to escalating threat sophistication and adversarial capability. SL-T (target) describes the security-level requirements the system is designed to meet; SL-A (achieved) describes the security-level requirements the system has actually been demonstrated to meet; SL-C (capability) describes the security-level requirements a component is capable of meeting.

Governance documentation should record the SL-T, SL-A, and SL-C values for each system and component, the date each was assessed, and the testing laboratory or assessor that performed the assessment. A claim that a system "meets SL 3" without distinguishing SL-T from SL-A is a frequent failure mode.

### 4. Distinguish organisation programmes from system requirements

IEC 62443-2-1 governs the IACS security programme at the organisation level. System-specific security requirements live in IEC 62443-3-3, and component requirements live in IEC 62443-4-1 and IEC 62443-4-2. Governance documentation should not blur the boundary between organisation-level programme requirements (IEC 62443-2-1) and system-level technical requirements (IEC 62443-3-3, IEC 62443-4-2).

### 5. Coordinate with adjacent industrial-cybersecurity frameworks

Industrial-cybersecurity governance typically operates alongside IEC 62443-2-1, IEC 62443-3-3, NIST SP 800-82 (industrial control systems security), the NIST Cybersecurity Framework, ISO/IEC 27001 (information security), ISO/IEC 27019 (energy-sector ISMS), and sectoral regulation (for example, the NIS2 Directive in the EU, the TSA pipeline security directives in the US, the NERC CIP standards for the bulk-electric system). The governance documentation should reference the operative edition of each framework and should not collapse them into a single narrative.

### 6. Sequence certification transitions

IEC 62443-2-1 is typically applied as a programme-establishment standard and is assessed by accredited certification bodies operating under ISO/IEC 17021-1, ISO/IEC 17065, or analogous accreditation schemes. The certification body's transition bulletin (or its analogue for a first-edition programme) is the operative source for transition governance.

### 7. Preserve historical evidence under the edition it was created for

Internal audit reports, programme documentation, security-level assessments, and corrective-action records that were assessed against IEC 62443-2-1:2010 should remain labelled with the edition under which they were created. Reinterpreting legacy findings against a future edition without preserving the original edition breaks traceability.

### 8. Monitor amendments, corrigenda, and IEC TC 65/WG 10 output

IEC TC 65/WG 10 is the working group responsible for the 62443 series. Governance should subscribe to TC 65/WG 10 publications and the IEC catalogue alerts for amendments, corrigenda, and interpretations. A change-log artefact should record the date of each change, the operative edition affected, and the affected clause numbers.

## Controls and evidence

Version-transition evidence typically includes:

- a dated edition register recording the IEC 62443-2-1 edition consulted for each artefact;
- a family edition register recording the operative edition of each 62443 part consulted alongside IEC 62443-2-1;
- an IACS security-programme policy and documentation set that explicitly references the operative edition;
- security-level assessments (SL-T, SL-A, SL-C) stored with the assessment date and the assessor;
- certification body bulletins, planned audit dates, and certificate-issuance conditions;
- internal audit reports stored with the edition reference under which they were assessed;
- adjacent-framework map listing each industrial-cybersecurity framework consulted and its operative edition; and
- training and competency records showing staff were briefed on the operative edition and on the security-level definitions.

## Validation

Validation that the IACS security programme continues to meet IEC 62443-2-1:2010 requirements typically draws on:

- internal audits against the operative edition by auditors trained on IACS security;
- external certification audits by an accredited certification body, where the organisation elects to pursue certification;
- management review minutes that explicitly reference the operative edition and the transition status;
- corrective action closure and effectiveness review under the operative edition;
- certification body's public register of certified clients, where certification is granted;
- sectoral regulator findings, where the IACS is in a regulated sector; and
- where applicable, ISASecure certifications issued by the ISA Security Compliance Institute against the operative 62443 parts.

## Failure correction

Common transition failures include:

- citing IEC 62443-2-1 without an edition in policy or customer-facing material;
- citing "IEC 62443" generically without specifying the part or edition;
- pairing IEC 62443-2-1 with an edition of IEC 62443-3-3 from a different edition cycle without documenting the discrepancy;
- conflating SL-T, SL-A, and SL-C;
- conflating organisation-level programme requirements with system-level technical requirements;
- treating IEC 62443 application as equivalent to compliance with sectoral IACS regulation;
- failing to update programme documentation when an adjacent part of the 62443 series is re-edited;
- mixing industrial-cybersecurity, information-security, and IT-cybersecurity frameworks into a single document that fails to identify the operative edition of each standard; and
- ignoring amendments, corrigenda, or interpretations issued against IEC 62443-2-1 or the 62443 series more broadly.

A corrective action should document the edition under which the failure occurred, the operative edition that should have been used, the disposition of historical evidence, and the owner of the re-issued artefact.

## Limitations

IEC 62443-2-1:2010 is a programme-establishment standard. Conformance with IEC 62443-2-1 does not equate to compliance with sectoral IACS regulation, with NERC CIP, with NIS2, or with other sectoral requirements. The standard does not prescribe specific technical security controls or product-selection criteria.

The 62443 series is large and multi-part. Each part has its own edition cycle, and transitions in one part do not automatically trigger transitions in another. Governance must track the series as a family rather than treat IEC 62443-2-1 in isolation.

## Canonical sources

- IEC — IEC 62443-2-1:2010, *Industrial communication networks — Network and system security — Part 2-1: Establishing an industrial automation and control system security program*: https://webstore.iec.ch/publication/7039
- IEC TC 65/WG 10 — Industrial-process measurement, control and automation / Security for industrial process measurement and control — Networks and systems: https://www.iec.ch/dyn/www/f?p=103:7:0::::FSP_ORG_ID:1276

## Scope note

This article describes version and reference governance for IEC 62443-2-1. It does not reproduce the standard, declare conformance, or substitute for the operative edition, an accredited certification body, or the organisation's IACS security-programme documentation.