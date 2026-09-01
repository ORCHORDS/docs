# Syft SBOM Generation into Deployment Gates

**Issue:** A Software Bill of Materials enumerates every package baked into a container image, and teams that generate SBOMs only after a release cannot answer the most common post-incident question: "is this CVE in any of our running images?". Syft produces a high-fidelity SBOM directly from an image or filesystem, but the operational value comes from integrating the SBOM into deployment gates so that vulnerable packages stop at the policy boundary instead of reaching runtime.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## SBOM Formats Syft Produces

Syft supports CycloneDX (1.4, 1.5, 1.6) and SPDX (2.2, 2.3) as output formats. CycloneDX is the more deployment-gate-friendly format because its schema includes explicit hashes, licenses, and a vulnerability extension point that Grype and other scanners consume directly. SPDX is the more legal-compliance-friendly format because it carries the precise license text and copyright fields that procurement workflows expect. Generate both formats and store them side by side: CycloneDX drives the gate, SPDX feeds the legal system.

The output is a JSON document whose structure is determined by the format's schema. CycloneDX's BOM includes a `components` array; each component has a `purl` (package URL), a `version`, and a hash set. The `purl` is the field that downstream tools match against vulnerability databases, and the hash set is what makes the SBOM verifiable against the image's actual contents. Without purls, the SBOM is just an inventory; with purls, it is an actionable index.

## Where SBOM Generation Belongs

SBOM generation belongs in the image build pipeline, immediately after the image is built and before it is pushed to a registry. Syft can run against the local image directly or against an image reference in a registry; the local invocation is faster and produces a result before the image leaves the build environment. The output is signed (typically with cosign's `--attachment sbom` flag) and pushed alongside the image, so consumers can fetch the SBOM by image reference.

The build pipeline should also produce a per-build SBOM inventory that is uploaded to a separate SBOM storage system. The signing attestation is fine for runtime verifiability but is awkward to query at scale; a separate store that indexes SBOMs by image digest and component purl allows the team to answer ad hoc queries like "show me all images that contain libfoo@1.2.3" without iterating every signed manifest.

## Gate Construction

The gate runs Grype (or equivalent) against the SBOM and rejects the deployment if the vulnerability scan returns any finding above a configured severity threshold. Grype consumes the same SBOM formats Syft produces, so the gate can be implemented as a downstream stage in the same pipeline: Syft generates, Grype scans, the pipeline gates on the result. The gate must run before any image reaches a long-lived registry tag; otherwise, a vulnerable image may persist in the registry after the gate has been bypassed for a separate deployment.

The severity threshold should be configurable per environment. Development environments may allow high-severity findings with a known mitigation; production environments should reject anything above medium. Store the thresholds in version control alongside the gate definition so the policy is auditable. The gate should also fail closed on scanner errors: a transient failure to reach the vulnerability database should not auto-pass the deployment, because the operator cannot be sure the image is clean.

## Integration With Cosign And Attestations

Syft's SBOM can be attached to an image as a cosign attestation, a feature that lets policy controllers verify the SBOM at admission time. The attestation is a signed statement of the form "this SBOM was generated for image X by build Y at time Z". The policy controller fetches the SBOM from the registry, verifies the signature against the public key, and runs the vulnerability scan inline. This is the only way to make the gate work in admission-controller scenarios where the deployer cannot run arbitrary scanners.

The in-toto attestation format is the standard container security attestation; Syft produces output that can be converted to in-toto via cosign's `attach attestation` command. The conversion requires an in-toto predicate type declaration; Syft uses the `https://cyclonedx.org/bom` predicate type for CycloneDX SBOMs. Configure the policy controller to recognize this predicate type and reject images that lack the attestation.

## Failure Modes

The most damaging failure is the gate running against a stale vulnerability database. Grype caches its database locally; without regular updates, the gate may pass a vulnerable image because the database has not yet learned about a recent CVE. Configure the database update as a precondition for the gate; the build pipeline should fail if the database is more than 24 hours old. Critical CVEs may be added within hours of disclosure, so a 24-hour window is the maximum acceptable latency.

A second failure is an SBOM that lists a package but does not capture the file paths it includes. CycloneDX supports a `targetFiles` field for each component; Syft populates this field for some package managers but not all. Without file paths, the SBOM cannot be cross-referenced against a vulnerability's affected file list, producing false positives or false negatives depending on the package layout. Validate that the SBOM includes file paths for the package managers the build pipeline actually uses.

A third failure is the gate allowing images with vulnerabilities that have a known exploit. Some vulnerability databases include exploit-availability metadata (KEV catalog, EPSS); the gate should treat any finding with known exploit availability as a hard fail, regardless of CVSS score. The CVSS score is a measure of severity, not exploitability; an exploitable moderate CVE is more dangerous than an unexploitable critical CVE. Configure the gate with both dimensions and document the precedence.

## Canonical sources

1. https://github.com/anchore/syft
2. https://github.com/anchore/grype