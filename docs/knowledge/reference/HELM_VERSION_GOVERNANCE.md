---
title: Helm Chart Packaging and Release Manager Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Helm project (helm/helm); CNCF graduated; documentation at helm.sh
---

# Helm Chart Packaging and Release Manager Version Governance

## Overview

This card governs how `orchords-docs` evaluates the Helm CLI, the chart format, OCI distribution, plugin lifecycle, and the surrounding tool ecosystem (Helmfile, Argo CD, Flux CD). It is the reference input for any KB card that cites chart packaging, release rollback semantics, or secret handling during `helm install`/`helm upgrade`.

## Versioning model

The Helm project carries two orthogonal versions:

| Component | Scheme | Notes |
|---|---|---|
| Helm CLI | SemVer, ~3 minor releases / year | 3.x is the current line; 4.0 in preview |
| Chart format (apiVersion) | `v1` (Helm 3), `v2` (Helm 2, deprecated), `v3` (proposed) | `v1` is the supported format; `v2` is rejected by Helm 3 |

- Chart `apiVersion: v1` is the supported contract for Helm 3.
- The proposed `apiVersion: v2` adds dependency locking, schema files (`values.schema.json`), and library charts; expect an opt-in window before CLI 4.0.
- The CLI version support window is current minor and the previous minor (N-1); security backports land on N-1 only.

References: `https://helm.sh/docs/`, `https://github.com/helm/helm/releases`.

## Helm client vs cluster version skew

- The Helm CLI is a thin client that talks to the cluster kube-apiserver; it does not embed a Kubernetes version.
- A given Helm CLI minor supports a defined Kubernetes version range documented in `helm version --short --client` and the release notes.
- Pin the CLI to a version that supports the cluster's `kubectl` minor ± 1; never run a CLI that is two minors ahead of the kube-apiserver.
- Keep the CLI image and `kubectl` image sourced from the same upstream release (e.g., both from a curated distroless or `bitnami/kubectl`) so `--kube-version` short-circuits match.

References: `https://helm.sh/docs/topics/version_skew/`.

## OCI registries and chart provenance

- Helm 3 supports OCI registries (`oci://registry.example/chart`) natively; the `helm registry login` flow is the only supported authentication path.
- Chart provenance: `helm package --sign` produces a provenance file signed with a cosign key (post-Helm 3.7, PGP signatures are deprecated). Verification is `helm install --verify`.
- Always store charts in OCI registries that support immutable tags; mutable tags break provenance chains.
- Pin charts by digest (`oci://registry/chart@sha256:...`) for production installs; tag-only references are not acceptable for high-trust environments.

References: `https://helm.sh/docs/topics/registries/`, `https://helm.sh/docs/topics/provenance/`.

## Plugin and chart repository lifecycle

- Plugins are versioned per author; there is no central registry of compatible Helm versions. Pin plugins by commit/tag and verify their `Downloader` interface against the running CLI minor.
- Chart repositories that have moved to OCI must be re-added via `helm repo add` and consumed with `oci://`; HTTP chart repositories are deprecated but still supported.
- Library charts (`type: library`) must be packaged into a `helm dependency build` step; never install a library chart directly.
- Mirror upstream repositories to an internal OCI registry; do not allow CI to reach external registries during `helm install`.

## Helmfile / Argo CD / Flux CD interactions

- **Helmfile**: declarative spec that wraps multiple `helm` invocations; pin the `helmfile` binary to a patch release and lock the CLI binary it shells out to. State is tracked in a `helmfile.yaml` and release selectors are stored in `helmfile.d/`.
- **Argo CD**: treats Helm charts as one of three source types. `argocd-image-updater` watches container image tags and triggers Helm re-renders. Pin the Argo CD version to a release that supports the running Helm chart API (see `ARGOCD_APPLICATIONSET_GOVERNANCE.md`).
- **Flux CD**: HelmRelease controller (Helm Operator successor) uses `helm-controller`; pin both the controller and the chart; Flux tracks release revisions internally and supports automated rollback on health-check failure.

## Upgrade and rollback semantics

- `helm upgrade --install` is idempotent; it creates the release if absent and upgrades if present. Always pass `--atomic` for production to roll back on failed hooks.
- `helm rollback <release> <revision>` restores a prior release revision from in-cluster secret state (`sh.helm.release.v1.<release>`); the rollback is atomic but does not undo cluster-side side effects (PVCs, CRD drift).
- Helm retains a configurable history (`--history-max`, default 10); prune old revisions before applying security releases that change CRDs.
- Use `--wait` and `--timeout` to fail fast on hung hooks; never run an upgrade in CI without `--wait`.

## Secrets handling on install

- `helm install` accepts `--set`, `--values`, and `--set-string`; secrets must never appear in plaintext flags or in committed `values.yaml` files.
- Use `helm secrets` (a plugin wrapping Mozilla SOPS) to decrypt on-the-fly values; the decrypted payload still appears in the rendered manifest unless the chart explicitly uses `lookup` and templated `Secret` resources.
- The in-cluster release secret (`sh.helm.release.v1.<release>`) stores the rendered manifest, including any rendered `Secret` literals; treat it as a sensitive resource and gate it with RBAC.
- For high-trust environments, prefer External Secrets Operator or Sealed Secrets to materialize secrets at runtime rather than committing them to the chart.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07.
