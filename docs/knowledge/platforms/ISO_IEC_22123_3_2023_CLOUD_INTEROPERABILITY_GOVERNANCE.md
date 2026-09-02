# ISO/IEC 22123-3:2023 Cloud Interoperability Governance

## Purpose

Govern the application of ISO/IEC 22123-3:2023 (cloud computing — Part 3: Interoperability) so that cloud service interoperability is treated as an explicit architectural property: where workloads and data can move between providers, the interoperability surface is designed, constrained deliberately, and validated, rather than assumed from marketing claims of open standards.

## Scope

Applies to every multi-cloud or cloud-exit-capable architecture the studio operates. Covers interoperability surface identification, portability constraint documentation, and interoperability validation. Does not cover service level objectives (covered by compute capability guidance) or cloud security controls (covered by cloud security guidance).

## Workflow

1. Identify the interoperability surface per workload: the interfaces and artefacts through which it consumes cloud services — compute interfaces, storage APIs, identity federation, deployment descriptors, and data formats.
2. Classify each surface element as standardized (portable across providers), provider-specific (portable with rework), or provider-locked (portable only through data export and rebuild); record the classification with rationale.
3. Constrain provider-locked elements deliberately: each one requires a documented exit cost estimate, a business justification, and a review date; accidental lock-in without a recorded decision is a governance violation.
4. Prefer standardized interfaces where they meet functional and operational requirements; where a provider-specific interface is chosen, record what the standardized alternative lacked.
5. Validate interoperability claims by exercise, not assertion: schedule periodic portability tests that deploy the workload to the secondary target and exercise its critical paths.
6. Track interoperability regressions: when a provider interface change breaks the secondary target, the fix lands in the interoperability register with root cause and prevention.
7. Reassess the interoperability surface when the workload's cloud service dependencies change; new dependencies enter the register with classification before production use.

## Controls and evidence

- Interoperability register per workload: surface element, classification, rationale, and review date.
- Exit cost estimates and business justifications for provider-locked elements.
- Portability test results: date, target environment, critical paths exercised, and outcome.
- Interoperability regression records with root cause analysis.

## Validation

- Sample one workload's interoperability register and confirm every provider-locked element has a current justification and review date.
- Confirm the most recent portability test deployed and exercised the workload's critical paths on the secondary target.
- Confirm new cloud dependencies in the period were classified before production use.

## Failure correction

- **Provider-locked element without justification** → classify it, estimate exit cost, and either justify or remediate toward a standardized interface before the next review.
- **Portability test fails** → record the regression, fix the incompatibility, and re-run the test; two consecutive failures escalate to architecture review.
- **Surface drift (new dependency unclassified)** → classify immediately and add dependency review to the workload's change gate.

## Limitations

- Interoperability validated by exercise is point-in-time; provider interface changes can invalidate it between tests.
- Standardized interfaces do not guarantee operational equivalence; performance and feature differences remain and need separate evaluation.
- Full portability is rarely free; the register exists to make lock-in a priced decision, not a forbidden one.

## Scope note

This article is part of the platforms leaf. Cross-reference: `ISO_IEC_22123_1_2023_CLOUD_OVERVIEW_GOVERNANCE.md`, `ISO_IEC_22123_CLOUD_REFERENCE_ARCHITECTURE.md`, and `NIST_SP_800_145_CLOUD_COMPUTING_DEFINITION.md`.

## Canonical sources

- ISO/IEC 22123-3:2023 — Information technology — Cloud computing — Part 3: Interoperability: https://www.iso.org/standard/85749.html
- ISO/IEC 22123-1:2023 — Cloud computing — Part 1: Concepts and vocabulary: https://www.iso.org/standard/85747.html
- ISO/IEC 22123-2:2023 — Cloud computing — Part 2: Reference architecture: https://www.iso.org/standard/85748.html
- ITU-T Y.3501 (06/16) — Cloud computing - Framework and high-level requirements: https://www.itu.int/rec/T-REC-Y.3501
- NIST SP 800-145 — The NIST Definition of Cloud Computing: https://csrc.nist.gov/publications/detail/sp/800-145/final
