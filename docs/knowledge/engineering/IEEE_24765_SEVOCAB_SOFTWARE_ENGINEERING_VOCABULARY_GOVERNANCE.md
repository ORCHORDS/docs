# IEEE 24765 SEVOCAB Software Engineering Vocabulary Governance

## Purpose

IEEE 24765, *Systems and software engineering — Vocabulary* (SEVOCAB), provides the authoritative glossary for systems and software engineering terms, maintained as a live database (SEVOCAB) with the standard published from it. Terms are harmonized across IEEE and ISO/IEC usage wherever the source standards agree.

Engineering organizations should anchor their terminology to SEVOCAB so that documents, reviews, and metrics use terms with defined meanings — preventing the definition drift that makes requirements and test documents ambiguous across teams.

## Scope

Applies to the studio's engineering documentation terminology practice. Covers term adoption, local glossary governance, and conflict resolution between local usage and SEVOCAB definitions. Does not cover domain-specific vocabularies (telecom, medical) beyond their software engineering intersection.

## Workflow

1. Adopt SEVOCAB as the primary terminology reference for engineering documentation; the live database (sevocab.com) reflects current harmonized entries, with the published standard as the citable snapshot.
2. Build the local glossary as a mapping: local terms map to SEVOCAB entries where they exist; genuinely local terms (product names, internal concepts) are defined locally and marked as such.
3. Resolve definition conflicts in favor of SEVOCAB: where a team's usage differs from the SEVOCAB definition, either the usage changes or the local term is renamed; silent divergence is the failure mode.
4. Cite the standard snapshot in governed documents: formal documents cite IEEE 24765 (year) for terminology; live database consultation supports day-to-day work.
5. Gate terminology at review: requirements and test document reviews check glossary terms against the mapping, catching drift at the review gate rather than post-ambiguity.
6. Track vocabulary evolution: SEVOCAB is maintained continuously; periodic re-mapping catches redefinitions that would silently change governed documents' meanings.
7. Feed disputes to the source: terminology disputes resolve by reading the SEVOCAB entry and its source standards, not by seniority or habit.

## Controls and evidence

- Local glossary with SEVOCAB mappings and locally-defined flags.
- Terminology check evidence in document review records.
- Citation of the 24765 snapshot in governed documents.
- Periodic re-mapping records tracking definition changes.

## Validation

- Sample 10 glossary terms from a governed document and confirm each maps to a current SEVOCAB entry or a flagged local definition.
- Confirm terminology checks appear in the sample's review records.
- Confirm the last re-mapping ran within the committed cadence.

## Failure correction

- **Term used divergently from SEVOCAB definition** → correct the usage or rename the local term; both the document and the glossary entry are updated together.
- **Unmapped term in a governed document** → map it at review; unmapped terms block approval.
- **Re-mapping overdue** → run it and assess affected documents for silently changed meanings.

## Limitations

SEVOCAB is descriptive of standards usage, not legislation — communities (agile, SRE) use terms with different shades, and forcing SEVOCAB precision onto community vocabulary is friction without value; govern the formal documents, not the conversation. The live database and the published standard can differ slightly in freshness.

## Scope note

This article is part of the engineering leaf. Cross-reference: `IEEE_29148_2018_REQUIREMENTS_ENGINEERING_GOVERNANCE.md`, `ISO_IEC_IEEE_29119_1_2022_TESTING_CONCEPTS_GOVERNANCE.md`, and `ISO_IEC_25010_2011_SOFTWARE_PRODUCT_QUALITY_MODEL.md`.

## Canonical sources

- IEEE 24765 — Systems and software engineering — Vocabulary: https://standards.ieee.org/ieee/24765/
- SEVOCAB — Software and Systems Engineering Vocabulary (live database): https://sevocab.com/ or https://www.computer.org/csdl/magazine/so
- ISO/IEC/IEEE 12207:2017 — Software life cycle processes (terminology source): https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:12207:ed-2
- ISO/IEC 25010 — System and software quality models (quality terminology): https://www.iso.org/obp/ui/#iso:std:iso-iec:25010
- ISO — Online Browsing Platform (ISO terminology): https://www.iso.org/obp/ui/
