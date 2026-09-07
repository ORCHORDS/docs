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

### Step 1 — Pick the scan type

1. Use `image` scanning in container image build pipelines.
2. Use `fs` scanning for source repositories (IaC, app source, dependency trees).
3. Use `k8s` scanning for cluster manifests and live manifests (`trivy k8s`).
4. Use `sbom` scanning to gate previously generated SBOMs.

### Step 2 — Configure severity gates

5. Define the policy gates: for example `CRITICAL` blocks, `HIGH` requires owner approval via PR check, `MEDIUM` warns.
6. Express them as `--severity` plus exit code (`--exit-code 1`) and as a SARIF post-process pass.
7. Exclude false positives via the Trivy ignore file (`trivy.yaml`) or via the VEX document; never by mutating upstream SBOMs.
8. Re-baseline the gate list whenever a new package family is introduced.

### Step 3 — Wire the pipeline

9. Invoke trivy in CI with `--format sarif --output trivy.sarif` plus a human-readable table artifact.
10. Cache the Trivy DB between runs (key off Trivy DB timestamp) to keep CI fast.
11. Sign the scan image as well as the build image where supply-chain attestation is in scope.

### Step 4 — Upload and route findings

12. Upload SARIF to the security dashboard; use `trivy convert sarif` only when the upstream format is non-SARIF.
13. Tag findings with repository, pipeline run ID, and SBOM hash so they remain traceable.
14. Fan out alert routing by severity; route CRITICAL findings to on-call within one business hour.
15. Attach the matching VEX statement to each waived finding so auditors can trace the suppression.

### Step 5 — Tune and verify

16. Compare pre- and post-adoption finding counts; alert on a sudden drop, which usually signals a misconfigured gate.
17. Periodically reverify that `--exit-code` and SARIF upload still occur on the same run.
18. Audit the VEX file quarterly and remove entries no longer present in fresh scans.

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
