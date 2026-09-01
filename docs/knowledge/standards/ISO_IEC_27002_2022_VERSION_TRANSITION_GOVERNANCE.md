# ISO/IEC 27002:2022 Version Transition Governance

## Purpose

This article describes how an organization records, governs, and transitions between editions of **ISO/IEC 27002**, *Information security, cybersecurity and privacy protection — Information security controls*. The current stable edition at the time of writing is the second edition, ISO/IEC 27002:2022, which restructures the controls catalog from 14 control objectives into 93 controls organised under four themes — organisational, people, physical, and technological — and introduces a five-attribute taxonomy (control type, information security properties, cybersecurity concepts, operational capabilities, and security domains) that aligns with ISO/IEC 27001:2022 Annex A.

The article is governance guidance. It is not a substitute for the operative text of the standard, an audit programme, or an ISMS-specific Statement of Applicability.

## Scope

ISO/IEC 27002 is a guidance standard. It does not contain normative requirements; requirements live in ISO/IEC 27001. ISO/IEC 27002 provides implementation guidance for the controls enumerated in ISO/IEC 27001:2022 Annex A and is the canonical reference when an organisation needs to describe *how* an Annex A control is implemented. Where ISO/IEC 27002 controls are cited in evidence (for example, in a SoA, a control matrix, or a customer-facing trust document), the edition cited must be the operative edition.

Because ISO/IEC 27002:2022 is referenced by ISO/IEC 27001:2022, an organisation that upgrades its ISMS to ISO/IEC 27001:2022 typically also needs to upgrade the ISO/IEC 27002 edition used for control guidance. The standards do not, however, share a single combined transition window, and the certification body determines how the upgrade interacts with the audit cycle.

## Version governance workflow

### 1. Pin the operative edition and the date consulted

Every reference to ISO/IEC 27002 controls must include the edition (for example, ISO/IEC 27002:2022). The catalogue page on iso.org records the publication date, the abstract, and the normative reference list, and these fields are sufficient to reconstruct the edition consulted at the time a control mapping was made. Unversioned references such as "ISO 27002 control 5.1" are not reliable across the 2013 and 2022 editions because control identifiers and the four-attribute structure changed materially.

### 2. Capture the structural transition explicitly

A control-by-control delta between ISO/IEC 27002:2013 and ISO/IEC 27002:2022 is a foundational artifact for any transition. The 2013 edition organised 114 controls under 14 control objectives; the 2022 edition reorganises 93 controls under 4 themes with 5 attributes each. Controls are added (for example, threat intelligence, information security for use of cloud services, ICT readiness for business continuity), merged (for example, addressing information security within supplier agreements consolidated related 2013 controls), retired (for example, controls wholly subsumed by other entries), and renumbered. The transition delta should be retrievable for the duration of any audit cycle that began under the prior edition.

### 3. Reissue implementation guidance under the new attribute taxonomy

Documentation that previously grouped controls by objective (for example, A.6 Organisation of information security) should be reorganised under the four-theme taxonomy (organisational, people, physical, technological) where the document is used as guidance. The five-attribute taxonomy can be retained as a cross-reference but should not become a parallel control numbering scheme. Reuse of legacy guidance under 2013 control identifiers is acceptable only when the document is labelled as historical reference and the current guidance under 2022 identifiers is provided alongside it.

### 4. Update mappings to ISO/IEC 27001 and dependent standards

ISO/IEC 27002:2022 controls map one-to-one (with attributes) to ISO/IEC 27001:2022 Annex A controls. Cross-document evidence that mixes 2013 control identifiers with 2022 annex identifiers is a frequent transition failure. A control matrix that maps to both editions should retain the 2013 reference for historical findings and the 2022 reference for current use, with a dated migration record.

Where ISO/IEC 27002:2022 is used to support ISO/IEC 27017 (cloud), ISO/IEC 27018 (PII in public clouds), ISO/IEC 27035 (incident management), or ISO/IEC 27701 (PIMS) controls, the dependent standards should also be tracked against their own edition cycles. A claim that ISO/IEC 27002:2022 supports ISO/IEC 27018:2019 is acceptable but should be explicit.

### 5. Manage language and translation versions

National member bodies publish language-specific editions of ISO/IEC 27002, and translations may lag the English text. Where a control interpretation depends on a non-English edition, the translation consulted should be recorded alongside the language-neutral reference. Discrepancies between translations should be resolved against the English normative reference.

### 6. Monitor amendments and corrigenda

ISO/IEC 27002:2022 may be amended rather than re-edited between major cycles. The ISMS function should subscribe to the ISO catalogue alert, monitor ISO/IEC JTC 1/SC 27 standing committee output, and record amendments, corrigenda, and interpretations under a change-log artefact.

## Controls and evidence

Version-transition evidence typically includes:

- a dated edition register listing the ISO/IEC 27002 edition consulted for each artefact in the ISMS;
- a transition delta document mapping 2013 controls to 2022 controls, including additions, mergers, retirements, and renumberings;
- a re-issued control matrix with 2022 control identifiers and a retained historical mapping to 2013 controls;
- a re-issued Statement of Applicability reflecting the new Annex A structure and the controls guidance edition used;
- implementation guidance documents reorganised under the four-theme taxonomy with versioned historical copies;
- training records showing staff were briefed on the 2022 attribute structure; and
- a change-log capturing amendments, corrigenda, and translation revisions.

## Validation

Validation that the controls catalog remains coherent typically draws on:

- internal reviews against the current edition, with a record of the edition consulted;
- external audits by an accredited certification body, which will record the ISO/IEC 27001 edition audited and the ISO/IEC 27002 edition cited for guidance;
- management review minutes that explicitly note the operative ISO/IEC 27002 edition;
- corrective actions tracked under the edition they were raised against;
- cross-references between the ISMS documentation, the SoA, and customer-facing trust documentation that all show the same edition; and
- where applicable, accreditation-body or certification-body bulletins that describe how the edition change is being administered.

## Failure correction

Common transition failures include:

- using unversioned ISO/IEC 27002 control identifiers in evidence or mappings;
- assuming a control from the 2013 edition has the same identifier, attribute set, or guidance in the 2022 edition;
- mixing ISO/IEC 27002:2013 and ISO/IEC 27002:2022 control references in the same matrix;
- failing to update implementation guidance when the controls were merged or split across the transition;
- destroying the 2013 implementation guidance before historical audit findings lose their interpretive value;
- treating ISO/IEC 27002 as normative when it is a guidance standard; and
- failing to record the translation edition where a non-English reference is used.

A corrective action should document the edition under which the failure occurred, the operative edition that should have been used, the disposition of the historical artefact, and the owner of the re-issued artefact.

## Limitations

ISO/IEC 27002:2022 is a guidance standard, not a certification basis. Certification is assessed against ISO/IEC 27001. ISO/IEC 27002 does not on its own define which controls apply to a given organisation; the applicability decision is made under the ISMS's risk assessment and is recorded in the Statement of Applicability.

The five-attribute taxonomy in ISO/IEC 27002:2022 is a categorisation model, not a numbering scheme, and re-numbering controls under a parallel attribute scheme should be avoided. Where organisations add their own attribute or control tags, those should be clearly distinguished from the ISO-defined attributes.

## Canonical sources

- ISO — ISO/IEC 27002:2022, *Information security, cybersecurity and privacy protection — Information security controls*: https://www.iso.org/standard/75652.html
- ISO/IEC JTC 1/SC 27 — Standing committee page on information security, cybersecurity and privacy protection: https://www.iso.org/committee/45306.html

## Scope note

This article describes version and reference governance for ISO/IEC 27002. It does not reproduce the standard's control text, declare conformance, or substitute for the operative edition, an accredited certification body, or an ISMS-specific Statement of Applicability.