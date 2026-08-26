# NIST SSDF third-party component governance

**Issue:** Third-party packages, build tools, hosted actions, models, and services can enter a product without a consistent acceptance record, leaving teams unable to show why a component was trusted or how it will be maintained.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Treat every externally sourced component as a governed dependency. Use the final NIST SP 800-218 SSDF 1.1 as the active baseline. NIST published an initial public draft of SSDF 1.2 in December 2025, but a draft must not silently replace the approved baseline.

## Controls

1. Record the component name, exact version or immutable digest, source, owner, license, intended use, and transitive-dependency exposure.
2. Prefer authoritative registries and publisher-controlled sources. Verify signatures, attestations, checksums, or immutable commit identifiers where the ecosystem supports them.
3. Define acceptance rules for known vulnerabilities, maintenance activity, provenance, release integrity, licensing, and replacement feasibility.
4. Keep the dependency inventory connected to the repository and deployed artifact. A spreadsheet detached from builds is not sufficient evidence.
5. Assign an owner and review trigger for each exception. Time-bound exceptions and document the compensating control.
6. Monitor for new advisories and upstream abandonment. Removal or replacement is an explicit lifecycle state, not an informal cleanup task.
7. Include build services, CI actions, model weights, base images, and code generators; governance is not limited to runtime libraries.

## Verification

- Rebuild from a clean environment and confirm resolved component digests match the approved inventory.
- Sample dependencies and trace each from declaration through lockfile/SBOM to the shipped artifact.
- Test that a prohibited source, unpinned reference, or expired exception fails the policy gate.
- Review the baseline when NIST publishes a final revision; label draft-driven experiments separately.

## Gotchas

- A lockfile improves repeatability but does not establish publisher identity or safety.
- A vulnerability scan is a point-in-time signal, not supplier governance.
- “Latest” tags and floating action references can change without a repository diff.
- Do not claim SSDF conformance from a single tool; the framework describes organizational practices and tasks.

## Sources

- [NIST Secure Software Development Framework project](https://csrc.nist.gov/projects/ssdf)
- [NIST SP 800-218, SSDF Version 1.1](https://csrc.nist.gov/pubs/sp/800/218/final)
- [NIST initial public draft announcement for SSDF 1.2](https://www.nist.gov/news-events/news/2025/12/secure-software-development-framework-ssdf-version-12-available-public)
