# SBOM Generation Tools

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your organization needs to produce a Software Bill of Materials (SBOM) for
compliance (EU Cyber Resilience Act, US Executive Order 14028, PCI DSS 4.0)
or supply chain security, but you do not know which tool to use, which format
to generate, or how to integrate SBOM generation into your CI/CD pipeline.

## Context

An SBOM is a machine-readable inventory of every component (direct and
transitive dependencies, OS packages, container layers) in your software.
Two standard formats dominate: CycloneDX (ECMA-424, preferred for security)
and SPDX (ISO/IEC 5962, preferred for licensing). In 2026, CycloneDX 1.6
has the broadest tool support and is the recommended default for most teams.

## Tool comparison

| Tool | Maintainer | Formats | Languages/Targets | Best for |
|---|---|---|---|---|
| **Syft** | Anchore | CycloneDX, SPDX | 20+ languages, containers, filesystems | Most versatile standalone CLI; pairs with Grype for vuln scanning |
| **cdxgen** | OWASP/CycloneDX | CycloneDX | 20+ languages, auto-detection | CycloneDX-native; supports SBOM, CBOM, OBOM, SaaSBOM types; reachability analysis |
| **Trivy** | Aqua Security | CycloneDX, SPDX | Containers, filesystems, git repos | All-in-one scanner (SBOM + vuln + misconfiguration) |
| **Microsoft SBOM Tool** | Microsoft | SPDX | .NET, npm, pip, Maven, Go | SPDX-focused; used internally by Microsoft |
| **CycloneDX plugins** | CycloneDX project | CycloneDX | Per-language (Maven, npm, pip, etc.) | Deep per-ecosystem accuracy |

## CI/CD integration

```yaml
# GitHub Actions example: generate SBOM on every release
name: SBOM
on:
  push:
    tags: ['v*']
jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Generate SBOM with Syft
      - uses: anchore/sbom-action@v0
        with:
          format: cyclonedx-json
          output-file: sbom.cdx.json

      # Scan SBOM for vulnerabilities with Grype
      - uses: anchore/scan-action@v4
        with:
          sbom: sbom.cdx.json
          fail-build: true
          severity-cutoff: high

      # Attach SBOM to release
      - uses: softprops/action-gh-release@v2
        with:
          files: sbom.cdx.json
```

```bash
# CLI examples

# Syft: generate CycloneDX SBOM from a container image
syft myapp:latest -o cyclonedx-json > sbom.cdx.json

# cdxgen: auto-detect project type and generate SBOM
cdxgen -o sbom.cdx.json

# Trivy: generate SBOM from filesystem
trivy fs --format cyclonedx --output sbom.cdx.json .
```

## Format guidance

- **Default:** CycloneDX 1.6 (JSON). Broadest tool support in 2026. Ratified
  as ECMA-424.
- **If SPDX required:** generate both formats natively (Syft supports dual
  output). Some US federal contracts require SPDX specifically.
- **Do not convert between formats** — conversion loses information. Generate
  natively in each required format.

## Best practices

1. **Generate on every release tag** — a release without a matching SBOM is
   a compliance gap.
2. **Store with release artifacts** — attach the SBOM to the GitHub release,
   container registry, or artifact repository.
3. **Scan SBOMs continuously** — new CVEs affect already-shipped software.
   Re-scan stored SBOMs against updated vulnerability databases.
4. **Include transitive dependencies** — direct-only SBOMs miss 80%+ of the
   attack surface. All tools listed above include transitives by default.
5. **Sign your SBOMs** — use Sigstore/cosign to sign SBOMs so consumers can
   verify authenticity.

## Gotchas

- **Trivy supply chain compromise (March 2026)** — Trivy's distribution
  channel was compromised twice in coordinated attacks. Many teams moved
  primary SBOM generation to Syft or cdxgen. If using Trivy, verify binary
  checksums and pin versions.
- **Language-specific accuracy varies** — no single tool is equally accurate
  across all ecosystems. Test your tool against your actual dependency tree
  and verify completeness.
- **Container vs. application SBOM** — scanning a container image produces
  an OS-package SBOM. Scanning the source code produces an application-
  dependency SBOM. You likely need both.
- **SBOM ≠ vulnerability report** — an SBOM lists components; a
  vulnerability scan correlates components against CVE databases. You need
  both steps.
- **Build-time vs. runtime dependencies** — dev dependencies (test
  frameworks, linters) should be excluded from production SBOMs. Configure
  your tool to distinguish production from dev dependencies.

## Related

- `documentation/categories/compliance/sbom-generation-distribution-cicd.md`
- `documentation/categories/compliance/eu-cyber-resilience-act-product-security-lifecycle.md`
- `documentation/categories/security/sbom-vulnerability-scanning.md`
- `documentation/categories/security/supply-chain-integrity-sigstore.md`
- `documentation/categories/security/slsa-supply-chain.md`

## Source URLs (verified 2026-08-16)

- SBOM generation tools compared — https://sbomify.com/2026/01/26/sbom-generation-tools-comparison/
- Best SBOM tools 2026 buyer's guide — https://bestdefense.io/blog/best-sbom-tools-a-2026-buyers-guide/
- cdxgen 2026 — https://appsecsanta.com/cdxgen
- How to generate CRA-compliant SBOMs — https://cra-decoded.com/blog/posts/cra_sbom_pipeline/
- SBOM tools compared: Syft vs Trivy vs CycloneDX — https://secure-pipelines.com/ci-cd-security/sbom-tools-compared-syft-trivy-cyclonedx-cli/
