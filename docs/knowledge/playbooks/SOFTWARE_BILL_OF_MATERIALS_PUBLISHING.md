---
title: "Software Bill of Materials Publishing"
owner: "Supply Chain Security"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "Every release of a published artifact, new consumer contract requiring SBOM, or quarterly completeness review."
scope: "All released artifacts — container images, binaries, libraries, firmware — that consumers can fetch and verify."
inputs:
  - "Build manifest and lock files"
  - "Build provenance attestation"
  - "Release identifier and distribution channel"
  - "SBOM format policy and consumer contract requirements"
plan:
  - "Step 1: Generate the SBOM at build time using the documented toolchain and format (SPDX or CycloneDX)."
  - "Step 2: Validate the SBOM for completeness — every direct and transitive dependency captured with name, version, supplier, and license."
  - "Step 3: Sign the SBOM with the build provenance attestation; bind the SBOM to the artifact identifier."
  - "Step 4: Publish the SBOM to the documented location alongside the artifact; include the SBOM in the release manifest."
  - "Step 5: Notify consumers of the SBOM availability and the verification procedure."
  - "Step 6: Re-validate on every refresh of dependencies or of the build toolchain; record the regeneration."
  - "Step 7: Capture residual actions for any SBOM that fails completeness validation."
evidence:
  - "SBOM artifact with build provenance signature"
  - "Completeness validation report"
  - "Release manifest with SBOM reference"
  - "Consumer notification record"
  - "Regeneration log"
escalation:
  - "SBOM fails completeness validation on a regulated release — escalate to Release Manager and Security."
  - "Consumer requires SBOM and none is available — escalate to Release Manager and Service Owner."
completion:
  - "SBOM published for every release of every in-scope artifact."
  - "Completeness validation recorded."
  - "Consumers notified."
exceptions:
  - "Internal-only artifacts explicitly marked out of scope; documented in the release policy."
related:
  - "SBOM_GENERATION_VERIFICATION.md"
  - "SBOM_COMPLETENESS_REVIEW.md"
  - "BUILD_ARTIFACT_PROVENANCE.md"
