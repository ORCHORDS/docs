# Helm Chart Adoption Playbook

## Purpose

Adopt Helm as the primary packaging and release mechanism for Kubernetes workloads, with version skew, provenance, OCI, and upgrade safety covered.

## Audience

Platform engineers, application teams using or planning to chart their workloads, SREs.

## Pre-conditions

- `docs/knowledge/reference/HELM_VERSION_GOVERNANCE.md` reviewed and version skew matrix internalized.
- Helm CLI pinned in `tools/helm/<version>` and verified via `helm version --short`.
- OCI registry target identified (e.g., `oci://ghcr.io/<org>/charts`) or self-hosted Harbor/Quay project provisioned.
- Chart provenance strategy decided: `helm package --sign` with a documented cosign key reference.
- `values.schema.json` authored and validated by `helm lint`.

## Procedure

### Step 1 — Install and pin the Helm CLI

1. Pin the Helm CLI to the version declared in `HELM_VERSION_GOVERNANCE.md`.
2. Verify the install: `helm version --short` and `helm env | grep HELM_BIN`.
3. Document the binary path in the platform bootstrap script so every developer and CI runner resolves the same version.

### Step 2 — Choose the OCI registry target

1. Confirm the OCI registry namespace and write permissions for CI.
2. Log in from CI: `helm registry login ghcr.io -u <ci-user> -p <token>` using a short-lived token.
3. Decide the tag convention (e.g., `<chart>-<appVersion>-<chartVersion>`) and document it alongside `Chart.yaml`.

### Step 3 — Author the chart skeleton

1. Run `helm create <chart-name>` and prune the templates directory to only the manifests you ship.
2. Edit `Chart.yaml`: set `apiVersion: v2`, `name`, `type: application`, `version`, and `appVersion`.
3. Populate `values.yaml` with safe defaults and require overrides through `values.schema.json`.

### Step 4 — Lint, template, and dry-run

1. `helm lint ./<chart>` and resolve every error before tagging.
2. `helm template release ./<chart> -f ci/values.yaml | kubeconform -strict -summary` to validate rendered manifests.
3. `helm install release ./<chart> --dry-run --debug` against a sandbox cluster to surface rendering issues.

### Step 5 — Sign and publish

1. `helm package ./<chart> --sign --key <key-name> --keyring ./keys.pub` to produce a signed `.tgz`.
2. `helm push <chart>-<version>.tgz oci://ghcr.io/<org>/charts` to publish.
3. Attach cosign signature and SBOM to the OCI artifact; record the digest in the release notes.

### Step 6 — Upgrade with atomicity

1. `helm upgrade --install release oci://ghcr.io/<org>/charts/<chart> --version <ver> -f values.yaml --atomic --wait --timeout 10m`.
2. Add a `pre-upgrade` hook that validates schema and a `post-upgrade` hook that runs smoke tests.
3. On any failure, `--atomic` reverts to the last successful revision automatically; confirm via `helm history release`.

## Rollback

- Use `helm rollback release <revision>` to return to a known-good revision, then verify with `helm status release`.
- If install-level secrets leaked, run `helm uninstall release` and scrub the namespace plus any associated PVCs.
- Restore the prior OCI tag with its original provenance attached; never overwrite an existing tag without preserving the previous digest.

## References

- `docs/knowledge/reference/HELM_VERSION_GOVERNANCE.md`
- `docs/knowledge/reference/COSIGN_VERSION_GOVERNANCE.md`
- Helm version skew: https://helm.sh/docs/topics/version_skew/
- Helm OCI registries: https://helm.sh/docs/topics/registries/
- Helm chart provenance: https://helm.sh/docs/topics/provenance/
