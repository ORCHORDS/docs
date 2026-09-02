# ISO/IEC/IEEE 29119-1:2022 Testing Concepts Governance

## Purpose

ISO/IEC/IEEE 29119-1:2022, *Software and systems engineering — Software testing — Part 1: General concepts*, defines the vocabulary and conceptual model for the 29119 series: test process model, test levels, test types, test techniques, and test basis concepts that the operational parts (29119-2 process, 29119-3 documentation, 29119-4 techniques) depend on.

Teams applying the 29119 series should cite Part 1 for terminology alignment so that test plans, reports, and process definitions use the series' defined terms consistently rather than local dialects.

## Scope

Applies to the studio's software testing practice wherever the 29119 series is the governing reference. Covers terminology alignment, the layered process model concept, and test level/type/technique classification. Does not cover specific process implementation (Part 2), templates (Part 3), or technique mechanics (Part 4).

## Workflow

1. Adopt the Part 1 conceptual model as the terminology baseline: organizational test policy → test strategy → test management → dynamic/later-cycle test processes, with the four-layer model anchoring where decisions belong.
2. Classify testing activity using the series' distinctions: test levels (unit, integration, system, acceptance) by the stage and scope of the item under test, not by who performs it.
3. Distinguish test types (functional, non-functional, structural, change-related) from test techniques (black-box, white-box, experience-based): a test level uses types and applies techniques — conflating them muddies planning.
4. Bind every test to a test basis: the documents or agreements from which test conditions derive; tests without a traceable basis are exploratory by declaration, not by omission.
5. Use Part 1's definitions in test documentation: deviation from series terminology in governed documents requires a glossary entry mapping local terms to Part 1 terms.
6. Feed terminology conformance into tooling: test management tools configured with levels/types/techniques matching the series' taxonomy produce comparable metrics across projects.
7. Revisit terminology alignment when the series evolves: later editions re-balance concepts, and test process assets drift without periodic re-mapping.

## Controls and evidence

- Terminology mapping document (local terms → 29119-1 terms) for governed test documentation.
- Test level and type classification per project recorded in the test plan.
- Test basis trace records: test conditions linked to basis documents.
- Tool configuration evidence showing taxonomy alignment.
- Periodic terminology re-mapping records.

## Validation

- Sample one project's test plan and confirm level/type/technique classification follows the Part 1 taxonomy.
- Confirm test basis links exist for non-exploratory test conditions in the sample.
- Confirm the terminology mapping document covers terms actually used in the sample documentation.

## Failure correction

- **Local dialect displacing series terms in governed documents** → add the mapping entry or correct the document; unmapped local terms are flagged at review.
- **Test without a declared basis** → classify it explicitly as exploratory or attach a basis; the silent middle is where coverage claims go soft.
- **Taxonomy drift after tool changes** → re-align tool configuration and record the mapping.

## Limitations

Part 1 is definitional; enforcement mechanics live in Parts 2-4. Organizations with strong existing testing traditions (ISTQB-based) find substantial overlap and should map rather than replace. The series is software-testing scoped; hardware and safety testing carry their own standards.

## Scope note

This article is part of the engineering leaf. Cross-reference: `IEEE_1012_2016_VERIFICATION_AND_VALIDATION.md`, `IEEE_1028_2008_REVIEW_TYPES_SELECTION_GOVERNANCE.md`, and `ISO_IEC_25040_2024_QUALITY_EVALUATION_GOVERNANCE.md`.

## Canonical sources

- ISO/IEC/IEEE 29119-1:2022 — Software and systems engineering — Software testing — Part 1: General concepts: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:29119:-1
- ISO/IEC/IEEE 29119-2 — Test processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:29119:-2
- ISO/IEC/IEEE 29119-3 — Test documentation: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:29119:-3
- ISO/IEC/IEEE 29119-4 — Test techniques: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:29119:-4
- ISTQB — Certified Tester Foundation Level syllabus (terminology comparison): https://www.istqb.org/
