# ISO/IEC 25051:2014 RUSP Quality Requirements Governance

## Purpose

ISO/IEC 25051:2014, *Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — Requirements for quality of Ready to Use Software Product (RUSP) and instructions for testing*, specifies quality requirements and test instructions for ready-to-use software products — off-the-shelf software delivered for use by third parties without development involvement.

Organizations producing RUSP should apply 25051 so that product quality claims, documentation requirements, and the accompanying test evidence meet the standard a procurer or certification scheme will check against.

## Scope

Applies to the studio's ready-to-use software products. Covers RUSP quality requirements, documentation obligations, and test instruction conformance. Does not cover custom software quality agreements (contract-specific) or the SQuaRE evaluation process (25040).

## Workflow

1. Determine RUSP applicability: the product is delivered as-is to users without custom development; COTS products, packaged software, and SaaS with fixed functionality fall under the concept's scope.
2. Meet the documentation requirements: product description, user documentation, and optionally a verification report — the product description states what the product does, its requirements, and its boundaries truthfully.
3. Ensure the product description's claims are testable: every functional claim in the description corresponds to demonstrable functionality; over-claiming in descriptions is the primary RUSP defect class.
4. Follow the standard's test instructions: functional coverage against the description, installation and uninstall testing, documentation review against actual behavior — testing oriented to what a user and evaluator will verify.
5. Maintain the documentation-behavior match: releases change behavior; documentation updates are part of the release, not an afterthought.
6. Provide the evidence trail: test results tied to description claims, retained per release, available to certification schemes and major procurers on request.
7. Align with certification schemes where the market requires: schemes (historically including national RUSP certification programs) layer administrative requirements on 25051's technical base.

## Controls and evidence

- RUSP applicability determination per product.
- Product description with testable claims.
- User documentation with release-linked updates.
- Test results mapped to description claims per release.
- Documentation-behavior review records.
- Certification scheme documentation where applicable.

## Validation

- Sample five claims from the product description and confirm test evidence exists for each.
- Confirm user documentation matches current release behavior for sampled features.
- Confirm installation/uninstall test records exist for supported platforms.

## Failure correction

- **Claim without test evidence** → add the test or amend the claim; untestable claims are removed at review.
- **Documentation-behavior mismatch** → correct documentation or behavior within the release process; mismatches found by users are quality escapes.
- **Missing evidence for a scheme submission** → run the gap tests before submission.

## Limitations

25051 addresses RUSP specifically; software with development agreements between supplier and acquirer uses contract-based quality requirements instead. The 2014 edition's testing instructions predate SaaS-era delivery; continuous delivery products adapt the per-release evidence obligations to their cadence while keeping claim-test traceability intact.

## Scope note

This article is part of the engineering leaf. Cross-reference: `ISO_IEC_25040_2024_QUALITY_EVALUATION_GOVERNANCE.md`, `ISO_IEC_25010_2011_SOFTWARE_PRODUCT_QUALITY_MODEL.md`, and `ISO_IEC_IEEE_29119_1_2022_TESTING_CONCEPTS_GOVERNANCE.md`.

## Canonical sources

- ISO/IEC 25051:2014 — SQuaRE — Requirements for quality of Ready to Use Software Product (RUSP) and instructions for testing: https://www.iso.org/obp/ui/#iso:std:iso-iec:25051:ed-2
- ISO/IEC 25010:2011 — SQuaRE — System and software quality models: https://www.iso.org/obp/ui/#iso:std:iso-iec:25010:ed-1
- ISO/IEC 25040 — SQuaRE — Evaluation process: https://www.iso.org/obp/ui/#iso:std:iso-iec:25040
- ISO/IEC/IEEE 29119-3 — Test documentation: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:29119:-3
- ISO/IEC 26514 — User documentation: https://www.iso.org/obp/ui/#iso:std:iso-iec:26514
