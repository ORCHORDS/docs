# ISO/IEC/IEEE 26514:2022 User Documentation Governance

## Purpose

ISO/IEC/IEEE 26514:2022, *Systems and software engineering — Design and development of information for users*, specifies requirements for designing and developing information for users (user documentation in its broad sense: manuals, help, embedded assistance) within systems and software development.

Documentation teams should apply 26514 so that user information is designed for the users' tasks, structured consistently, developed with the product lifecycle, and validated with users rather than written as an afterthought at release time.

## Scope

Applies to the studio's user-facing information products: manuals, online help, in-product guidance, release notes addressed to users. Covers information design, structure, development process, and validation. Does not cover API reference generation (engineering tooling practice) or marketing content.

## Workflow

1. Design information for tasks, not features: each unit of user information addresses what a user is trying to accomplish; feature-inventory documentation forces users to reverse-engineer tasks.
2. Structure consistently per the standard's requirements: consistent heading hierarchy, task-oriented organization, and navigational structures (contents, index, search hooks for online) applied uniformly across the information set.
3. Integrate documentation development with the product lifecycle: information units are planned, drafted, and completed against the same milestones as the software; documentation lagging release is a release blocker, not a footnote.
4. Write from the standard's quality characteristics for information: accuracy, completeness, clarity, conciseness, findability, and freedom from defects — reviewed as requirements, not aspirations.
5. Manage information as configuration items: versioned with the product, reviewed for behavior matches, and released with the corresponding product version — the documentation-behavior match is the core quality control.
6. Validate with users: usability of the information itself is tested (can users complete tasks using the information alone); untested documentation ships on hope.
7. Handle multiple audiences deliberately: role-based or experience-based variants are planned structures, not duplicated manuals diverging silently.

## Controls and evidence

- Information plan mapping units to user tasks.
- Structure and style conformance records.
- Documentation lifecycle integration records (milestone-linked completion).
- Documentation-behavior review records per release.
- User validation results for the information set.
- Configuration management records for information products.

## Validation

- Sample one information unit and confirm it addresses a stated user task with review evidence.
- Confirm the documentation-behavior review ran for the last release.
- Confirm at least one user validation of the information set occurred within the committed cadence.

## Failure correction

- **Documentation-behavior mismatch found post-release** → correct within the release process and trace how the review gap occurred.
- **Task orientation absent (feature inventory)** → restructure the worst-affected units first; full restructure follows the plan.
- **User validation skipped** → run validation before the next release and add the gate.

## Limitations

26514's requirements add process discipline that small projects may scale down, but its quality characteristics apply at any size. Agile delivery compresses documentation milestones into iterations; the standard's requirements map onto definition-of-done items rather than separate phases. AI-assisted content generation lowers drafting cost but raises the documentation-behavior review's importance — generated text must still match behavior.

## Scope note

This article is part of the engineering leaf. Cross-reference: `ISO_IEC_25051_2014_RUSP_READY_TO_USE_GOVERNANCE.md`, `IEEE_24765_SEVOCAB_SOFTWARE_ENGINEERING_VOCABULARY_GOVERNANCE.md`, and `ISO_IEC_25019_2023_QUALITY_IN_USE_MODEL_GOVERNANCE.md`.

## Canonical sources

- ISO/IEC/IEEE 26514:2022 — Systems and software engineering — Design and development of information for users: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:26514:ed-2
- ISO/IEC/IEEE 26512 — Information for users of systems and software: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:26512
- ISO/IEC/IEEE 26531 — Content management for information for users: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:26531
- ISO/IEC 25019:2023 — SQuaRE — Quality-in-use model (user outcome quality): https://www.iso.org/obp/ui/#iso:std:iso-iec:25019:ed-1
- ISO 9241-110 — Interaction principles: https://www.iso.org/obp/ui/#iso:std:iso:9241:-110
