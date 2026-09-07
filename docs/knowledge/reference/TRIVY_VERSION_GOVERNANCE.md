---
title: Aqua Trivy Multi-Scanner Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://trivy.dev/ ; https://github.com/aquasecurity/trivy
---

# Aqua Trivy Multi-Scanner Version Governance

## 1. Purpose

This reference card governs the lifecycle of the **Aqua Trivy** scanner — the single-binary tool used for container image, filesystem, repository, Kubernetes, SBOM, and VEX output generation across ORCHORDS CI/CD pipelines.

## 2. Scope

In scope:

- Trivy CLI v0.55+ (and `trivy-operator` for in-cluster scans).
- Scanners: image, fs, rootfs, repo, k8s, cluster, sbom, license, secret, misconfig.
- Reporters: JSON, SARIF, SPDX JSON, CycloneDX JSON, OpenVEX, GitHub code-scanning.
- Database refresh: trivy-db and trivy-java-db.

Out of scope:

- Aqua Enterprise platform (we use Trivy OSS only).
- Trivy-action on Windows runners (use Linux runners).

## 3. Versioning policy

- Pin the Trivy CLI to a specific minor (e.g. `v0.55.1`); allow patch auto-update inside one minor.
- Refresh the trivy-db at least every 24 h via a scheduled CI job; cache the db tarball in object storage.
- For SBOM emission, always include `--format spdx-json` and `--format cyclonedx` simultaneously for downstream consumers.
- VEX emission uses `--vex` and references the OpenVEX 0.2 schema.

## 4. Compatibility matrix

| Trivy CLI | K8s (operator) | trivy-db | Notes |
| --- | --- | --- | --- |
| 0.50.x | 0.13.x | 2 | License scanner GA |
| 0.53.x | 0.15.x | 2 | SBOM-driven scan |
| 0.55.x | 0.17.x | 2 | OpenVEX output, K8s cluster scan |

## 5. Severity gating

| Severity | Action |
| --- | --- |
| UNKNOWN | Log only |
| LOW | Log only |
| MEDIUM | Warn in PR comment |
| HIGH | Block CI for production images |
| CRITICAL | Block CI for all images; open security ticket |

## 6. SBOM/VEX emission

- Every released image MUST have an SPDX 2.3 SBOM attached as an OCI artifact.
- VEX entries MUST be emitted whenever a CVE is triaged as `not_affected` or `fixed`.
- VEX MUST use OpenVEX 0.2; do not embed proprietary fields.

## 7. Pipeline integration

- Source stage: `trivy fs --scanners misconfig,secret` on PR diff.
- Build stage: `trivy image --format sarif` uploaded to GitHub Code Scanning.
- Deploy stage: `trivy-operator` schedules periodic scans in cluster; SARIF exported.

## 8. Upgrade procedure

1. Pull the new Trivy image and re-scan a representative set of test images.
2. Confirm all reporters still emit valid output.
3. Roll the operator across dev → stage → prod clusters.
4. Promote after 7 days of green scan results.

## 9. Rollback procedure

- `kubectl rollout undo deployment/trivy-operator -n trivy-system`.
- Past scans remain available in the SARIF history.

## 10. Observability

- Required metrics: `trivy_image_scan_total{registry,result}`, `trivy_vulnerabilities_total{severity,fix_state}`, `trivy_db_age_seconds`.
- Alert on `trivy_db_age_seconds` > 86400 (24 h) sustained 1 h.

## 11. References

- Trivy docs — https://trivy.dev/
- Trivy operator — https://github.com/aquasecurity/trivy-operator
- OpenVEX spec — https://github.com/openvex/spec
