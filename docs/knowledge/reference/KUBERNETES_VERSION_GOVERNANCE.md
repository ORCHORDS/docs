---
title: Kubernetes Version Governance (CNCF Kubernetes Releases)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Kubernetes project (https://kubernetes.io/), CNCF; Kubernetes release cadence (3 minor releases per year); SIG Architecture; Kubernetes 1.27 (April 2023), 1.28 (August 2023), 1.29 (December 2023), 1.30 (April 2024), 1.31 (August 2024), 1.32 (December 2024), 1.33 (April 2025), 1.34 (August 2025), 1.35 (December 2025)
---

# Kubernetes Version Governance (CNCF Kubernetes Releases)

## Scope

This card governs how `orchords-docs` evaluates Kubernetes versions and the surrounding ecosystem. It is the reference input for any KB card that cites Kubernetes, kubeadm, kubectl, container runtime, or cloud-managed Kubernetes (EKS / AKS / GKE).

## Why this card exists

Kubernetes ships three minor releases per year (≈ every 4 months). Each release brings deprecated APIs, new features, and security patches. The supported window per release is approximately 14 months (with extended support for N-3). A KB card that cites "Kubernetes" without binding to the version, supported window, and the upgrade path produces a cluster that drifts on first release update.

## Version support matrix (2026-09)

| Minor | Released | EoL (standard) | Notes |
|---|---|---|---|
| 1.31 | August 2024 | October 2025 | standard |
| 1.32 | December 2024 | November 2025 | standard |
| 1.33 | April 2025 | June 2026 | standard |
| 1.34 | August 2025 | September 2026 | standard |
| 1.35 | December 2025 | October 2026 | standard |
| 1.36 | April 2026 (planned) | November 2026 | upcoming |

Policy:

- Support the current minor and the previous minor (N-1) at any time.
- Upgrade window: ≤ 9 months after a new minor release.
- Vendor-managed Kubernetes (EKS / AKS / GKE) follows the vendor's support policy.

References: `https://kubernetes.io/releases/`, `https://kubernetes.io/releases/version-skew-policy/`.

## Version skew

- `kubelet` ≤ control plane minor version + 2.
- `kubectl` ≤ control plane minor version + 1.
- Container runtime: CRI-compatible (containerd ≥ 1.7, CRI-O ≥ 1.27).

## API deprecation

Kubernetes tracks API deprecation per release:

- Each beta API becomes GA or is removed.
- Each GA API is removed after ≥ 9 months of deprecation.
- Reference: `https://kubernetes.io/docs/reference/using-api/deprecation-guide/`.

Policy:

- Audit API usage per release: `kubectl api-resources --verbs=list -o name | xargs -I{} kubectl get {} -A -o yaml 2>/dev/null`.
- Identify deprecated APIs with `kubectl deprecations` or `pluto`.
- Migrate before the API is removed.

## Container runtime

| Runtime | Status |
|---|---|
| containerd ≥ 1.7 | supported |
| CRI-O ≥ 1.27 | supported |
| Docker (via dockershim) | removed in 1.24; deprecated for new deployments |

## Networking

- CNI: Cilium, Calico, Flannel, Weave.
- Service mesh: Istio, Linkerd, Cilium Service Mesh.
- Ingress: NGINX, HAProxy, Envoy Gateway, Traefik.
- Gateway API: SIG Network; supported in 1.30+.

## Storage

- CSI driver per cloud provider or vendor.
- In-tree drivers deprecated; migrated to CSI.
- Volume snapshot / restore per CSI spec.

## Authentication and authorization

- Authentication: bearer token (ServiceAccount), OIDC, Webhook.
- Authorization: RBAC (default), ABAC (deprecated), Webhook.
- ServiceAccount tokens: bound, projected (since 1.21).

## Pod Security

| Policy | Status |
|---|---|
| PodSecurityPolicy | removed in 1.25 |
| Pod Security Admission (PSA) | preferred; baseline / restricted / privileged |
| Kyverno | optional; Kyverno 1.10+ |
| OPA Gatekeeper | optional; 3.10+ |

## Mandatory pre-flight (before adopting a new Kubernetes cluster)

1. Version is within the supported matrix.
2. kubelet, kubectl, container runtime are compatible.
3. CNI / CSI / Ingress are configured.
4. Authentication is configured (OIDC).
5. Authorization is configured (RBAC).
6. Pod Security Admission is configured.
7. Backup / restore is wired.
8. Monitoring is wired.

## Upgrade procedure

1. Read release notes for the target minor.
2. Audit deprecated APIs.
3. Upgrade control plane first.
4. Upgrade node by node.
5. Validate workload.
6. Repeat for each minor increment (no skipping).

## Observability

- kube-state-metrics (gauge per object).
- node-exporter (host metrics).
- Prometheus + Grafana for time-series.
- OpenTelemetry for traces.
- Cluster events.

## Sources

- Kubernetes releases: `https://kubernetes.io/releases/`
- Version skew policy: `https://kubernetes.io/releases/version-skew-policy/`
- API deprecation: `https://kubernetes.io/docs/reference/using-api/deprecation-guide/`
- Pod Security Standards: `https://kubernetes.io/docs/concepts/security/pod-security-standards/`
- CNCF Kubernetes: `https://www.cncf.io/projects/kubernetes/`
