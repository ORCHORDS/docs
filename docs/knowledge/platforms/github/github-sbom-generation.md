# github-sbom-generation

**Issue:** Generating and exporting Software Bill of Materials (SBOM) from GitHub repos
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Enterprise customers and government contracts increasingly require an SBOM listing all dependencies. Teams need to generate SPDX or CycloneDX formatted SBOMs and attach them to releases.

## Pattern / Solution
GitHub provides a built-in SBOM export (SPDX 2.3 format) via the dependency graph API. For richer formats, use `anchore/sbom-action`.

**Download GitHub's built-in SBOM via API:**
```bash
gh api repos/OWNER/REPO/dependency-graph/sbom \
  --header "Accept: application/vnd.github+json" \
  > sbom.spdx.json
```

**Auto-attach SBOM to GitHub Release:**
```yaml
name: Release with SBOM

on:
  release:
    types: [published]

permissions:
  contents: write
  security-events: write

jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate SBOM (SPDX)
        uses: anchore/sbom-action@v0
        with:
          format: spdx-json
          output-file: sbom.spdx.json
          upload-artifact: false

      - name: Generate SBOM (CycloneDX)
        uses: anchore/sbom-action@v0
        with:
          format: cyclonedx-json
          output-file: sbom.cdx.json
          upload-artifact: false

      - name: Attach SBOMs to release
        run: |
          gh release upload "${{ github.event.release.tag_name }}" \
            sbom.spdx.json sbom.cdx.json
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Docker image SBOM with Syft:**
```yaml
      - name: Generate container SBOM
        uses: anchore/sbom-action@v0
        with:
          image: ghcr.io/${{ github.repository }}:${{ github.sha }}
          format: spdx-json
          output-file: container-sbom.spdx.json
```

**SBOM for compliance attestation:**
```bash
# Verify SBOM with cosign (supply chain security)
cosign attest --predicate sbom.spdx.json \
  --type spdxjson \
  ghcr.io/OWNER/REPO:latest
```

## Gotchas
- GitHub's built-in SBOM export only includes dependencies detected by the dependency graph — it requires the dependency graph to be enabled and supported lock files to be present
- SPDX and CycloneDX are different standards; some compliance requirements specify which one — check before generating
- The `anchore/sbom-action` scans the filesystem or container image; it doesn't use GitHub's dependency graph and may produce different results
- SBOM generation for container images requires the image to be pulled, which counts against registry egress
- SBOM files can be large (MBs for large dependency trees); don't commit them to the repo — attach to releases or store in object storage

## Related
- `github-dependency-review.md`
- `github-code-scanning-codeql.md`
- `github-actions-docker-build-push.md`
