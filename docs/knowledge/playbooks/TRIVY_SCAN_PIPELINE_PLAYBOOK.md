# Trivy Scan Pipeline Adoption Playbook

## Purpose

Provide a repeatable pipeline for adopting Trivy scanning across image, filesystem, Kubernetes manifest, and SBOM targets. The playbook enforces severity gates, supports VEX-based suppression, and produces SARIF results that can be uploaded to the engineering security dashboard.

## Audience

Security engineers, DevOps / platform engineers integrating Trivy into CI, and SREs operating the results dashboard.

## Pre-conditions

- Trivy CLI / container pinned per `docs/knowledge/reference/TRIVY_VERSION_GOVERNANCE.md` and DB update cadence agreed.
- Build environment can pull from a private registry and reach the Trivy DB source (or air-gap DB mirroring is configured).
- VEX document lives in the policy repo (`vex.json` or OpenVEX) and is co-located with the affected manifests.
- SARIF upload credentials and target endpoint exist; secrets injected via OIDC trust, not long-lived tokens.

## Procedure

1. Pick the scan type: `image` for container builds, `fs` for source and IaC trees, `k8s` for cluster and live manifests (`trivy k8s`), and `sbom` to gate previously generated SBOMs. Run multiple scanners in the same job when the asset warrants it.
2. Define severity gates: for example `CRITICAL` blocks, `HIGH` requires owner approval via PR check, `MEDIUM` warns. Express them as `--severity` plus `--exit-code 1` and as a SARIF post-process pass. Exclude false positives via `trivy.yaml` or the VEX document; never by mutating upstream SBOMs.
3. Invoke Trivy in CI with `--format sarif --output trivy.sarif` plus a human-readable table artifact. Cache the Trivy DB between runs (key off DB timestamp). Sign the scan image as well as the build image where supply-chain attestation is in scope.
4. Upload SARIF to the security dashboard; use `trivy convert sarif` only when the upstream format is non-SARIF. Tag findings with repository, pipeline run ID, and SBOM hash. Route CRITICAL findings to on-call within one business hour. Attach the matching VEX statement to each waived finding.
5. Compare pre- and post-adoption finding counts; alert on a sudden drop, which usually signals a misconfigured gate. Periodically reverify that `--exit-code` and SARIF upload still occur on the same run. Audit the VEX file quarterly and remove stale entries.

## Rollback

- Revert the workflow file to the prior pinned Trivy version and DB; the next run will use the prior baseline.
- If SARIF upload starts misrouting, hold the failing run, notify the dashboard owner, and re-export from the prior artifact.
- If a severity gate was wrong, raise it temporarily via workflow variable, open a policy change ticket, and never backdoor new ignores.
- Restore the prior SBOM where a Trivy change caused false positives on a clean artifact.

## References

- `docs/knowledge/reference/TRIVY_VERSION_GOVERNANCE.md`
- `docs/knowledge/operations/CNCF_TRIVY_VULNERABILITY_SCANNING_GOVERNANCE.md`
- `docs/knowledge/operations/infra/container-image-scanning-trivy-grype.md`
- https://aquasecurity.github.io/trivy/v0.57/docs/scanner/vulnerability/
- https://github.com/aquasecurity/trivy/blob/main/docs/docs/scanner/sbom.md
