# CNCF Helm Chart OCI Release Governance

## Purpose

Helm (CNCF Graduated) packages Kubernetes resources into charts and supports distribution through OCI registries (Helm 3.8+). The OCI release governance pattern captures the chart version, the OCI registry URL, the signing strategy (cosign, Helm provenance), the values-rendering pipeline, and the rollback procedure. Without explicit governance, OCI releases drift across environments and provenance verification becomes impossible.

## Current context and source status

Helm 3.14 (released 2024) and Helm 3.16 (released 2025) are the current supported versions. Helm 3.17 entered beta in mid-2026. The OCI registry support is GA in Helm 3.8 and later. The project follows the CNCF Graduated governance model.

## Governance pattern

1. Pin the Helm version and the chart version (`Chart.yaml`) in cluster bootstrap.
2. Distribute charts via OCI registries (for example `oci://registry.example.com/charts/myapp-1.2.3.tgz`); avoid plain HTTPS helm repo where OCI is available.
3. Sign the chart with cosign (keyless OIDC or KMS-backed key) and verify on install.
4. Render values with `helm template` or `helm lint` in CI; reject charts that fail lint.
5. Pin chart dependencies (`Chart.yaml` `dependencies[*].version`) with exact versions; update via Dependabot or Renovate.
6. Maintain a chart-OCI-registry inventory: registry URL, chart name, current version, signing key reference.
7. Use `helm install --wait --atomic` for production deployments to ensure rollback on failure.
8. Record the install command and rendered manifest in the deployment log.
9. Use `helm history` and `helm rollback` for documented rollback procedures.
10. Verify chart provenance (SLSA, cosign attestations) on each install.

## Validation and evidence

- Helm version pinned in cluster bootstrap.
- Chart OCI registry URL and version recorded in registry inventory.
- Chart signed with cosign; verification key registered.
- CI lint output clean; template render produces expected manifest.
- Production install uses `--wait --atomic`.
- Chart provenance verified (cosign verify, SLSA provenance attestation).

## Failure correction

Common defects include unsigned charts in production, un-pinned dependency versions, and missing rollback procedure. Corrective actions include enabling cosign signing in the release pipeline, pinning dependency versions, and adding `helm rollback` to the deployment runbook.

## Limitations

- Helm does not provide fine-grained canary or blue-green rollout (use Argo Rollouts or Flagger).
- Helm rollback retains the previous release but does not migrate PersistentVolume data.
- OCI registry authentication requires credential rotation handled outside Helm.
- Chart signing is not a substitute for SBOM attestation.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (Helm deployment topology), **engineering** (chart authoring conventions), **security** (chart signing and SBOM), and **templates** (chart skeleton template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- Helm documentation (CNCF Graduated): https://helm.sh/docs/
- Helm OCI registry support (CNCF Graduated): https://helm.sh/docs/topics/registries/
- Helm chart best practices (CNCF Graduated): https://helm.sh/docs/chart_best_practices/

Sources were verified on September 1, 2026.