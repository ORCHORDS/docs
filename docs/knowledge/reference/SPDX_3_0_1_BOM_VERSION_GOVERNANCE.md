# SPDX 3.0.1 BOM Version Governance

## Purpose

SPDX 3.0.1 is the current published SPDX specification and defines an open data model for communicating bill-of-materials information across software, build, AI, dataset, licensing, security, provenance, and related domains.

A BOM exchange should identify the SPDX specification version it conforms to so producers and consumers interpret the same model and serialization rules.

## Version semantics

SPDX 3.0.1 defines `specVersion` as a semantic-version value used to understand how an element should be parsed and interpreted. The specification states that incompatible changes increment the major version, backward-compatible feature changes increment the minor version, and backward-compatible bug fixes increment the patch version.

Exchange partners should therefore record the exact specification version they emit and support instead of using an ambiguous label such as only `SPDX 3`.

## BOM and profile model

SPDX 3 defines a core model that can be extended by profiles. A BOM is a collection of SPDX elements sharing context and can describe composition, provenance, licensing, vulnerabilities, quality information, and other product characteristics.

The Software profile covers artifacts such as packages, files, snippets, and software-related relationships. Other SPDX profiles cover additional domains such as AI or build information.

## Governance pattern

1. Record the exact `specVersion` for every generated SPDX 3 document or element set.
2. Identify which SPDX profiles the producer intentionally supports.
3. Validate required fields and relationships against the applicable profile and serialization rules.
4. Preserve immutable identifiers and integrity data needed to connect the BOM to the actual artifact or product revision.
5. Treat conversion from SPDX 2.x to 3.x as a model transformation, not a simple string-version replacement.
6. Test downstream tooling with the exact SPDX version/profile combination before making it a required exchange format.
7. Reject or quarantine unknown major versions rather than assuming backwards compatibility.
8. Retain the source artifact digest and BOM generation metadata so regenerated BOMs can be compared reproducibly.

## Profiles and minimal exchange

SPDX 3 profiles allow an exchange to constrain the model to a particular domain. The Lite profile provides a minimal normative subset aimed at simpler license-compliance/SBOM use cases.

A consumer should not assume a document contains every possible SPDX profile or every class of security/provenance data merely because it is valid SPDX 3.0.1.

## Failure modes

- Recording only `3.0` when the producer emitted 3.0.1 hides patch-level parsing expectations.
- Treating SPDX 3 as wire-compatible with SPDX 2.x without transformation can corrupt semantics.
- Assuming a valid Software-profile BOM includes vulnerability, build, or AI data overstates its scope.
- Accepting unknown major versions without validation can misinterpret incompatible models.
- Failing to bind a BOM to an immutable artifact identifier can leave consumers unsure which build it describes.

## Sources

- SPDX Specification 3.0.1 — Introduction: https://spdx.github.io/spdx-spec/v3.0.1/front/introduction/
- SPDX Specification 3.0.1 — Scope: https://spdx.github.io/spdx-spec/v3.0.1/scope/
- SPDX Specification 3.0.1 — `specVersion`: https://spdx.github.io/spdx-spec/v3.0.1/model/Core/Properties/specVersion/
- SPDX Specification 3.0.1 — SPDX Lite: https://spdx.github.io/spdx-spec/v3.0.1/annexes/spdx-lite/

## Scope note

This article describes format/version governance for SPDX 3.0.1 exchanges. It does not claim that a particular BOM is complete, accurate, or compliant with any external regulatory SBOM requirement.