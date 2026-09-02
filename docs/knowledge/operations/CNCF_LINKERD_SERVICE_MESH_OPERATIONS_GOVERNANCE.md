# CNCF Linkerd Service Mesh Operations Governance

## Purpose

Linkerd (CNCF Graduated) is a service mesh that adds mTLS, observability, and traffic management to Kubernetes workloads through a per-pod proxy (the Linkerd2-proxy, a hardened Rust proxy). The operations governance pattern captures the install method (linkerd install or Helm), the control-plane version, the identity issuance (default issuer vs external issuer), the proxy injection strategy (namespace labels), and the upgrade procedure. Without explicit governance, Linkerd proxies drift across clusters and mTLS coverage becomes inconsistent.

## Current context and source status

Linkerd 2.15 (released 2024), Linkerd 2.16 (released 2025), and Linkerd 24.x (released 2026, rebranded stable release line) are the current supported versions. The project follows the CNCF Graduated governance model. Linkerd2-proxy is a hardened Rust micro-proxy derived from the Tower service-mesh code paths.

## Governance pattern

1. Pin Linkerd control-plane and CLI versions in cluster bootstrap.
2. Install Linkerd via `linkerd install --crds | kubectl apply` or the official Helm chart; reject ad-hoc installs.
3. Use the default issuer for development; use an external issuer (Vault, cert-manager) for production.
4. Configure proxy injection via namespace labels: `linkerd.io/inject: enabled`.
5. Define per-namespace mTLS mode: `default` (cluster-wide mTLS) or `disabled` for specific namespaces.
6. Use `linkerd check` to validate the install and the upgrade.
7. Monitor Linkerd metrics: `tcp_*`, `http_*`, `grpc_*` request metrics per workload.
8. Document the upgrade procedure: install CRDs, install control-plane, validate with `linkerd check`.
9. Maintain a rollback procedure: `linkerd upgrade` to a previous stable version.
10. Document the multi-cluster mode (gateway, mirror, HA) and the federation trade-offs.

## Validation and evidence

- Linkerd control-plane and CLI versions recorded in cluster inventory.
- Install command committed to GitOps.
- Issuer configuration recorded (default or external).
- Proxy injection labels verified by `linkerd viz stat`.
- mTLS mode documented per namespace.
- `linkerd check` exits 0.
- Metrics dashboard deployed.
- Upgrade and rollback procedure tested in staging.

## Failure correction

Common defects include ad-hoc installs without version control, default issuer in production, and missing namespace labels causing partial mTLS coverage. Corrective actions include requiring install script in GitOps, enforcing external issuer in production, and validating injection coverage with `linkerd viz stat`.

## Limitations

- Linkerd does not provide HTTP-level routing policies (use Ingress or Gateway API).
- Linkerd does not integrate with non-Kubernetes services without manual proxy injection.
- Multi-cluster mode requires careful DNS and gateway planning.
- Linkerd2-proxy is hardened but does not substitute for application-layer authentication.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (Linkerd deployment topology), **security** (mTLS and identity issuance), **engineering** (service-mesh design patterns), and **templates** (Linkerd install template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- Linkerd documentation (CNCF Graduated): https://linkerd.io/docs/
- Linkerd GitHub repository (CNCF Graduated): https://github.com/linkerd/linkerd2
- Linkerd2-proxy GitHub repository (CNCF Graduated): https://github.com/linkerd/linkerd2-proxy

Sources were verified on September 1, 2026.