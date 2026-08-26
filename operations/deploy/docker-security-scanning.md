# docker-security-scanning

**Issue:** Integrating container image vulnerability scanning into CI/CD pipelines
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Container images accumulate OS and dependency CVEs silently. Without automated scanning, teams discover vulnerabilities only after exploitation. Scanning must be fast enough for CI and actionable enough for developers.

## Pattern / Solution
Trivy in CI (GitHub Actions):
```yaml
- name: Scan image with Trivy
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ghcr.io/myorg/myapp:${{ github.sha }}
    format: sarif
    output: trivy-results.sarif
    severity: CRITICAL,HIGH
    exit-code: '1'          # fail CI on critical/high
    ignore-unfixed: true    # ignore CVEs with no fix yet

- name: Upload Trivy results to GitHub Security
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: trivy-results.sarif
```

Dockerfile scanning with Hadolint:
```yaml
- name: Lint Dockerfile
  uses: hadolint/hadolint-action@v3.1.0
  with:
    dockerfile: Dockerfile
    failure-threshold: error
```

Grype for SBOM generation:
```bash
# Generate SBOM
syft ghcr.io/myorg/myapp:latest -o spdx-json > sbom.json

# Scan SBOM
grype sbom:sbom.json --fail-on critical
```

Registry-side scanning (ECR):
```bash
aws ecr describe-image-scan-findings \
  --repository-name myapp \
  --image-id imageTag=latest \
  --query 'imageScanFindings.findings[?severity==`CRITICAL`]'
```

.trivyignore (suppress known false positives):
```
# CVE-2022-12345 — not exploitable in our usage, tracked in JIRA-123
CVE-2022-12345
```

## Gotchas
- Scanning only at build time misses newly discovered CVEs in already-deployed images; add registry-scheduled scans
- Base image CVEs are not the app team's fault but still the app team's problem to fix via image updates
- Alpine-based images have far fewer CVEs than Debian/Ubuntu; use Alpine or distroless where possible
- `--ignore-unfixed` reduces noise but hides real risk; review unfixed CVEs quarterly
- SBOM attestation (cosign + SLSA) is increasingly required for supply chain compliance

## Related
- `docker-multi-stage-build.md`
- `container-image-tagging.md`
- `docker-compose-production.md`
