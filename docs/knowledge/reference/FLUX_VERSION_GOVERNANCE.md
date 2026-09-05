---
title: Flux CD GitOps Toolkit Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Flux CD; CNCF Flux project; fluxcd.io
---

# Flux CD GitOps Toolkit Version Governance

## Scope

This card governs how `orchords-docs` evaluates Flux CD across versions, controllers, and the GitOps Toolkit (GTKS) component model.

## Why this card exists

Flux CD is the canonical GitOps controller alongside Argo CD. Without an explicit card, the KB cites Flux practices that ignore the toolkit controllers (Source, Kustomize, Helm, Notification) and the v2 API.

## Versions

| Version | Status |
|---|---|
| 2.0–2.2 | legacy |
| 2.3–2.4 | current |
| 2.5+ | current |

References: `https://github.com/fluxcd/flux2/releases`.

## GitOps Toolkit

Flux is composed of controllers:

| Controller | Purpose |
|---|---|
| Source Controller | Git / Helm / Bucket / OCI |
| Kustomize Controller | apply Kustomize |
| Helm Controller | apply Helm releases |
| Notification Controller | webhooks, alerts |
| Image Reflector / Automation | image updates |
| Image Update Controller | auto-update |

References: `https://fluxcd.io/flux/components/`.

## CRDs

| CRD | API |
|---|---|
| `GitRepository` | `source.toolkit.fluxcd.io/v1` |
| `OCIRepository` | `source.toolkit.fluxcd.io/v1` |
| `Bucket` | `source.toolkit.fluxcd.io/v1` |
| `HelmRepository` | `source.toolkit.fluxcd.io/v1` |
| `Kustomization` | `kustomize.toolkit.fluxcd.io/v1` |
| `HelmRelease` | `helm.toolkit.fluxcd.io/v2` |
| `Alert` / `Provider` / `Receiver` | `notification.toolkit.fluxcd.io/v1` |
| `ImagePolicy` / `ImageRepository` | `image.toolkit.fluxcd.io/v1` |

## Sync strategies

- Apply (default).
- Replace (force).
- Force on annotations.
- Reconcile interval.

References: `https://fluxcd.io/flux/components/kustomize/kustomizations/`.

## Bootstrap

`flux bootstrap` initializes a cluster with:

- Git repository setup.
- Flux installation.
- Initial `Kustomization`.

References: `https://fluxcd.io/flux/cmd/flux_bootstrap/`.

## Cross-reference

| Domain | Card |
|---|---|
| Argo | `ARGO_VERSION_GOVERNANCE.md` |
| GitOps | `GITOPS_VERSION_GOVERNANCE.md` |
| Helm | `HELM_VERSION_GOVERNANCE.md` (deferred) |

## Sources

- Flux documentation: `https://fluxcd.io/flux/`
- Flux GitHub: `https://github.com/fluxcd/flux2`
- CNCF Flux: `https://www.cncf.io/projects/flux/`
- GitOps Toolkit: `https://fluxcd.io/flux/components/`
