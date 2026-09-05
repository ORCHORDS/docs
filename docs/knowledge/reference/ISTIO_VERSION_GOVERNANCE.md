---
title: Istio Service Mesh Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Istio project (https://istio.io/), CNCF; Istio 1.19 — 1.25 series; Solo.io enterprise distributions; Ambient mesh; CNCF Istio graduation (July 2023)
---

# Istio Service Mesh Version Governance

## Scope

This card governs how `orchords-docs` evaluates Istio versions and the supporting service-mesh ecosystem (Linkerd, Cilium Service Mesh, Consul Connect, AWS App Mesh). It is the reference input for any KB card that cites a service mesh.

## Why this card exists

Istio ships quarterly minor releases with rolling upgrade support between N and N-1. Each release brings API changes (VirtualService, DestinationRule, Gateway CRDs), security policy updates, and ambient-mesh progress. A KB card that cites Istio without binding to the version, supported-window, and control-plane / data-plane compatibility produces a deployment that breaks on first dependency update.

## Version support matrix (2026-09)

| Version | First release | EOL (support window ≈ 6 months) | Notes |
|---|---|---|---|
| 1.19 | November 2023 | May 2024 | stable |
| 1.20 | February 2024 | August 2024 | stable |
| 1.21 | May 2024 | November 2024 | stable |
| 1.22 | August 2024 | February 2025 | stable |
| 1.23 | November 2024 | May 2025 | stable |
| 1.24 | February 2025 | August 2025 | stable |
| 1.25 | May 2025 | November 2025 | current |
| 1.26 | August 2025 | February 2026 | upcoming |

Policy:

- Support the current minor and the previous minor (N-1).
- Upgrade window: ≤ 6 months after a new minor release.

References: `https://istio.io/latest/news/support/`.

## Sidecar / ambient

Istio supports two data-plane modes:

| Mode | Description |
|---|---|
| Sidecar (classic) | Envoy sidecar in every workload pod |
| Ambient | node-level ztunnel + per-service waypoint proxy; sidecar-less |

Policy:

- Sidecar mode is the production baseline.
- Ambient is emerging; production adoption requires careful review.

## API version

Istio uses `networking.istio.io/v1` for:

- `VirtualService`
- `DestinationRule`
- `Gateway`
- `ServiceEntry`
- `Sidecar`
- `EnvoyFilter`

Policy:

- Pin API version to `v1`; do not use deprecated `v1alpha` or `v1beta1`.

## mTLS policy

| Mode | Description |
|---|---|
| DISABLE | no mTLS |
| PERMISSIVE | mTLS when possible, plaintext fallback |
| STRICT | mTLS only |

Policy:

- STRICT mTLS is the production baseline.
- PERMISSIVE is acceptable during migration.
- DISABLE is forbidden for production.

## Authorization policy

Istio `AuthorizationPolicy` enforces RBAC / ABAC:

- `ALLOW` rules grant access.
- `DENY` rules deny access.
- `CUSTOM` rules use external authorization (OPA, custom).

Policy:

- Default-deny + explicit `ALLOW`.
- Wildcards permitted only at the mesh admin boundary.

## Telemetry

Istio emits:

- Access logs (envoy).
- Metrics (envoy, prometheus).
- Traces (envoy, otel, jaeger, zipkin).
- Service graph (Kiali).

## Mandatory pre-flight (before adopting a new Istio deployment)

1. Version is within the supported matrix.
2. mTLS policy is STRICT.
3. Authorization policies are wired.
4. Telemetry is wired.
5. Control-plane / data-plane compatibility is validated.
6. Sidecar injection is configured (or ambient is opted-in).

## Upgrade procedure

1. Read release notes for the target minor.
2. Validate API compatibility: `istioctl analyze`.
3. Upgrade control plane via `istioctl upgrade`.
4. Restart workloads to pick up the new sidecar.
5. Validate telemetry and policies.
6. Repeat for each minor increment.

## Cross-reference

| Domain | Card |
|---|---|
| Service mesh rollout | `SERVICE_MESH_MTLS_ROLLOUT_PLAYBOOK.md` |
| Kubernetes | `KUBERNETES_VERSION_GOVERNANCE.md` |
| Zero Trust | `NIST_SP_800_207_ZERO_TRUST_GOVERNANCE.md` |
| Workload identity | `WORKLOAD_IDENTITY_ROTATION_PLAYBOOK.md` |

## Observability

- `istio_request_total` (counter, per source/destination).
- `istio_request_duration_milliseconds` (histogram).
- `istio_request_error_count` (counter).
- `istio_tcp_bytes_received` / `istio_tcp_bytes_sent` (counter).
- `istio_sidecar_injection_count` (counter).
- `istio_mtls_failure_count` (counter).

## Sources

- Istio: `https://istio.io/`
- Istio support window: `https://istio.io/latest/news/support/`
- Istio security: `https://istio.io/latest/docs/concepts/security/`
- Istio Ambient: `https://istio.io/latest/docs/ambient/`
- Linkerd: `https://linkerd.io/`
- Cilium Service Mesh: `https://docs.cilium.io/en/latest/network/servicemesh/`
