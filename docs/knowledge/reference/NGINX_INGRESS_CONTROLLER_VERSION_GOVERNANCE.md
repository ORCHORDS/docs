---
title: NGINX Ingress Controller for Kubernetes Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: NGINX Ingress Controller project (kubernetes/ingress-nginx); Kubernetes SIG; documentation at kubernetes.github.io/ingress-nginx
---

# NGINX Ingress Controller for Kubernetes Version Governance

## Overview

This card governs how NGINX Ingress Controller (the upstream `kubernetes/ingress-nginx` controller, not the F5 NGINX-built variant) is versioned, deployed, and upgraded across Kubernetes clusters. It is the reference for any KB card that touches cluster ingress, TLS termination at the edge, WAF integration, or path-based routing on managed Kubernetes.

## Versioning model and the v1 vs v1.1+ controller split

- The project tags releases as `vMAJOR.MINOR.PATCH`, following semantic versioning; `controller-*` container images are published to `registry.k8s.io/ingress-nginx/controller`.
- The legacy line (a.k.a. "v1 controller") tracks NGINX 1.21–1.25 with the original Go controller binary; it remains on standard release support for cluster operators that have not yet migrated.
- The `v1.1+` line (sometimes referenced as the 1.10+ series) introduced the new Go module layout, plugin SDK, OpenTelemetry trace context propagation, and `IngressClass`-aware configuration merging; downstream charts (Helm `ingress-nginx` 4.x+) require this line.
- Maintain an N / N-1 support posture: ship the current minor plus the previous minor; security backports flow only into the most recent minor on each line.
- Treat any chart change that bumps `app.kubernetes.io/version` past a major boundary as a planned migration window, not a hot patch.

## HA deployment and rolling upgrades

- Run at least two controller replicas spread across zones; prefer three replicas on production clusters for quorum during node drains.
- Use the `RollingUpdate` strategy with `maxUnavailable: 0` and `maxSurge: 1` so the admission webhook never drops; set the pod disruption budget to `minAvailable: 1`.
- Terminate traffic on a stable `Service` of type `LoadBalancer` (cloud L4) or via a `NodePort`/host-network front end on bare metal; do not depend on a specific pod IP.
- Enable leader election (`--enable-leader-election=true`) so only one controller writes NGINX configuration at a time when running multiple replicas.
- For zero-downtime upgrades, configure the readiness probe on port `10246` and the liveness probe on `/healthz`; NGINX reloads happen only after a successful readiness transition.

## Ingress / HTTPRoute and CRDs

- Default to the `Ingress` API (`networking.k8s.io/v1`) for path- and host-based routing; pin `apiVersion` in manifests to avoid silent upgrades to `v1` from `extensions/v1beta1`.
- For advanced matching, retries, and traffic splitting, evaluate `HTTPRoute` from Gateway API (`gateway.networking.k8s.io/v1`); enable the Gateway API CRDs via the chart's `controller.gateway.enabled` flag.
- Treat `VirtualServer` and `VirtualServerRoute` (CRDs `k8s.nginx.org/v1`) as the supported path when policy, canary, or split-client behavior is needed; do not mix `Ingress` annotations and `VirtualServer` resources for the same hostname.
- Validate CRD compatibility with the chart version: each minor release pins CRD `schema` revisions and removes deprecated fields in a deprecation cycle.

## TLS termination posture (edge / SNI / passthrough)

- Edge termination (default): the controller terminates TLS using a `Secret`-mounted certificate; cipher list defaults follow Mozilla "Intermediate" profile.
- SNI passthrough: enable with `kubernetes.io/ingress.allow-http: "false"` and an `ssl-passthrough` annotation; the controller forwards TLS to the upstream without re-termination.
- Re-encrypt (TLS → upstream TLS): configure `proxy-ssl-secret` and `proxy-ssl-verify` annotations; the controller terminates TLS at the edge and re-establishes TLS to the backend pod.
- Manage certificates via cert-manager `Certificate` resources; do not hand-edit the `tls:` block of an `Ingress` once cert-manager owns the lifecycle.
- Honor HSTS at the edge (`hsts: "max-age=31536000"`), and forward `X-Forwarded-*` headers with `use-forwarded-headers: "true"` only when the upstream is trusted.

## ModSecurity / WAF integration

- ModSecurity is bundled in the controller container as an optional module; enable with `controller.enable-modsecurity: true` and ship an `OwaspModSecurityCRS` policy under `default-server-modsecurity`.
- Use the OWASP Core Rule Set (CRS) v3.3.x with the controller's bundled ModSecurity v2.9.x; pin via `controller.config.enable-owasp-modsecurity-crs: true` rather than rolling custom rules into the image.
- Watch the controller logs for `ModSecurity: Access denied` events; surface anomalies to the SIEM with the `log-format-escape-json: true` setting so JSON-line output survives ingestion.
- Disable the `SecRuleEngine` for trusted internal namespaces by mounting a per-snippet override; never disable globally for compliance-bound tenants.

## Rate limiting and auth

- Configure global rate limits via the `ConfigMap`: `limit-req-zone`, `limit-req-status`, and `limit-req-key` map to `limit_conn_zone` / `limit_req_zone` directives under the hood.
- For per-tenant limits, use the `VirtualServer` CRD's `rateLimit` field; it supports `rate`, `burst`, and `key` against `$binary_remote_addr` or a JWT claim.
- External auth is wired via `auth-url`, `auth-signin`, `auth-response-headers`, and `proxy_set_header` annotations; do not implement auth in NGINX snippets when an OIDC sidecar can be reached via a dedicated upstream.
- Use `jwt-auth` annotations for JWT validation; pin the JWKS URL and refresh interval, and rotate the `jwt-key` `Secret` outside of business hours.

## Helm upgrade and chart compatibility

- Pin the chart to a 3-segment version (`ingress-nginx/ingress-nginx: 4.x.y`); allow only `~>` ranges when upgrading patch releases.
- The Helm chart's `controller.image.digest` is the source of truth for the controller image; always set `controller.image.tag` and `controller.image.digest` together for reproducible rollouts.
- Chart 4.x line is required for Kubernetes 1.28+; chart 3.x is EoL and should not be used for greenfield clusters.
- Customizations belong under `controller.config` (the `nginx.conf` snippets map), not in custom `extraVolumes` that overwrite the NGINX config; this keeps upgrades deterministic.
- Run `helm diff upgrade ingress-nginx ingress-nginx/ingress-nginx --version x.y.z` against staging before promoting; CRD drift is a known upgrade failure mode and must be resolved first.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07. The card is also re-evaluated on every chart major bump, every controller minor that introduces a new CRD `schema` revision, and on any upstream security advisory that affects NGINX core or ModSecurity.

## References

- Upstream repository: `https://github.com/kubernetes/ingress-nginx`
- Documentation: `https://kubernetes.github.io/ingress-nginx/`
- Releases and changelog: `https://github.com/kubernetes/ingress-nginx/releases`
- Helm chart: `https://github.com/kubernetes/ingress-nginx/tree/main/charts/ingress-nginx`
- ModSecurity / OWASP CRS guide: `https://kubernetes.github.io/ingress-nginx/user-guide/third-party-add-ons/modsecurity/`
- Gateway API integration: `https://gateway-api.sigs.k8s.io/`
- cert-manager integration: `https://cert-manager.io/docs/usage/ingress/`
