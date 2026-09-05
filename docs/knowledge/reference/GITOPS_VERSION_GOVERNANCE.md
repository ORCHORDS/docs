---
title: GitOps and Argo CD / Flux Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: CNCF Argo Project (https://argoproj.github.io/); CNCF Flux Project (https://fluxcd.io/); OpenGitOps specification (https://opengitops.dev/)
---

# GitOps and Argo CD / Flux Version Governance

## Scope

This card governs how `orchords-docs` evaluates GitOps tooling — Argo CD and Flux — and the supporting OpenGitOps principles. It is the reference input for any KB card that cites declarative cluster management, application sync, or progressive delivery.

## Why this card exists

GitOps is the operational practice of declaring the desired cluster state in Git and reconciling it via an automated agent. Two ecosystems dominate: CNCF Argo (Argo CD, Argo Rollouts, Argo Workflows, Argo Events) and CNCF Flux (Flux CD, Flagger, Helm Operator, SOPS). Without an explicit card, the KB cites GitOps patterns that do not survive an audit.

## OpenGitOps principles

OpenGitOps is the CNCF / Finniture specification (1.0, 2024) that defines four principles:

1. **Declarative** — desired state is described declaratively.
2. **Versioned and Immutable** — desired state is stored in a versioned, immutable way (Git).
3. **Pulled Automatically** — agents pull the desired state and reconcile.
4. **Continuously Reconciled** — agents continuously observe and reconcile.

References: `https://opengitops.dev/`.

## Argo CD version matrix

| Version | First release | Status |
|---|---|---|
| 2.4.x | 2022 | stable |
| 2.6.x | 2022 | stable |
| 2.8.x | 2023 | stable |
| 2.9.x | 2023 | stable |
| 2.10.x | 2024 | stable |
| 2.11.x | 2024 | stable |
| 2.12.x | 2024 | stable |
| 2.13.x | 2025 | stable |
| 2.14.x | 2025 | current |

References: `https://github.com/argoproj/argo-cd/releases`.

## Flux CD version matrix

| Version | First release | Status |
|---|---|---|
| 2.0.x | 2022 | stable |
| 2.1.x | 2023 | stable |
| 2.2.x | 2023 | stable |
| 2.3.x | 2024 | stable |
| 2.4.x | 2024 | stable |
| 2.5.x | 2025 | stable |
| 2.6.x | 2025 | current |

References: `https://github.com/fluxcd/flux/releases`.

## Application definition

| Tool | Format |
|---|---|
| Argo CD | Application / ApplicationSet (CRD) |
| Flux | Kustomization, HelmRelease (CRD) |
| Helm | Chart (Helm v3) |
| Kustomize | kustomization.yaml |

Policy:

- Each application lives in its own Git repository (preferred) or subdirectory.
- Source-of-truth branch is `main`.
- Tags mark the production-recommended version.

## Sync strategies

| Strategy | Description |
|---|---|
| Apply | declarative apply (Argo / Flux) |
| Replace | replace resource on conflict |
| Sync wave | ordered rollout |
| Progressive delivery | canary / blue-green (Argo Rollouts, Flagger) |

## Mandatory pre-flight (before adopting a new GitOps tool)

1. OpenGitOps principles are documented.
2. The tool version is within the support matrix.
3. The repository structure is documented.
4. The sync policy is documented.
5. Secrets management is wired (SOPS, Sealed Secrets, External Secrets Operator).
6. RBAC is configured.

## Secrets management in GitOps

| Tool | Mechanism |
|---|---|
| SOPS | encrypted YAML/JSON files; key in KMS / KMS-AAD / KMS-GCP |
| Sealed Secrets | public-key-encrypted Kubernetes secrets |
| External Secrets Operator | pulls from external secret store (Vault, AWS Secrets Manager) |

Policy:

- Secrets are NEVER stored in plaintext.
- SOPS or External Secrets Operator is preferred.
- Sealed Secrets acceptable for edge cases.

## Progressive delivery

| Tool | Notes |
|---|---|
| Argo Rollouts | canary, blue-green, traffic shifting |
| Flagger | canary, A/B testing |
| Argo Workflows | DAG-based workflows |

Policy:

- Progressive delivery for any service exposed to customer traffic.
- Canary baseline: 5% canary for 10 minutes, then 25%, 50%, 100%.

## Observability

- `gitops_sync_status` (gauge, per app).
- `gitops_sync_duration_seconds` (histogram).
- `gitops_drift_count` (counter).
- `gitops_applications_healthy` (gauge).
- `gitops_applications_out_of_sync` (gauge).

## Sources

- OpenGitOps: `https://opengitops.dev/`
- Argo CD: `https://argoproj.github.io/argo-cd/`
- Flux CD: `https://fluxcd.io/`
- Argo Rollouts: `https://argoproj.github.io/argo-rollouts/`
- Flagger: `https://flagger.app/`
- SOPS: `https://github.com/getsops/sops`
- Sealed Secrets: `https://github.com/bitnami-labs/sealed-secrets`
- External Secrets Operator: `https://external-secrets.io/`
