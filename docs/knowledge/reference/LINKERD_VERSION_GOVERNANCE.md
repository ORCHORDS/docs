---
title: Linkerd Service Mesh Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-06
review-cycle: 180 days
next-review: 2027-03-05
source: Linkerd project release and reference documentation
---

# Linkerd Service Mesh Version Governance

## Scope

This card governs version interpretation, upgrade planning, and release-artifact selection for Linkerd service-mesh deployments.

## Current project versions

Linkerd 2.20 was announced on 2026-06-23. The project release page maps it to code tag `version-2.20` and edge release `edge-26.6.3`.

Linkerd 2.19 is the preceding project version and maps to code tag `version-2.19`.

The project distinguishes project versions, edge releases, and known distributions. Operators MUST verify the artifact source and support model they actually deploy instead of assuming that a project version label guarantees a particular distribution or support entitlement.

## Upgrade rules

- Run Linkerd pre-upgrade checks before changing the control plane.
- Review release notes for every crossed project version.
- Upgrade the control plane before intentionally rolling data-plane proxies to a new image.
- Confirm extension compatibility, including observability and multicluster components, before promotion.
- Preserve the cluster trust-anchor and identity configuration unless the change specifically includes identity rotation.
- Re-run health checks after the control-plane change and after data-plane rollout.

## Compatibility evidence

Record:

1. Linkerd project version and deployed artifact version.
2. Kubernetes version.
3. Control-plane component versions.
4. Proxy image version.
5. Enabled extensions.
6. Identity issuer and trust-anchor expiry window.
7. Pre-upgrade and post-upgrade check results.

## 2.20 operational note

Linkerd 2.20 includes rate-limit-aware load balancing, control-plane memory improvements, improved inbound metrics, and native sidecars as the default data-plane deployment type. Teams upgrading from an earlier release SHOULD verify assumptions around proxy lifecycle and metrics collection.

## Sources

- Linkerd releases: `https://linkerd.io/releases/`
- Linkerd 2.20 announcement: `https://linkerd.io/2026/06/23/announcing-linkerd-2.20/`
- Linkerd reference: `https://linkerd.io/docs/reference/`
