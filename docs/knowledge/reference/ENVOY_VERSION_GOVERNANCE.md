---
title: Envoy Proxy Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Envoy documentation; CNCF Envoy project; envoyproxy.io
---

# Envoy Proxy Version Governance

## Scope

This card governs how `orchords-docs` evaluates the Envoy proxy across versions, xDS APIs, and integration patterns (Ingress, Gateway API, Service Mesh).

## Why this card exists

Envoy is the canonical cloud-native L4/L7 proxy, the data plane of Istio, and the reference implementation for the Gateway API. Without an explicit card, the KB cites Envoy practices that ignore the rapid 6-week release cadence and the v3 xDS protocol.

## Versions

| Version | Status |
|---|---|
| 1.20–1.24 | legacy |
| 1.25–1.30 | current stable |
| 1.31–1.33 | current |

References: `https://github.com/envoyproxy/envoy/releases`.

Envoy has a 6-week minor release cadence. Patch releases are monthly.

## xDS APIs

| API | Use |
|---|---|
| `envoy.config.listener.v3.Listener` | listener config |
| `envoy.config.route.v3.RouteConfiguration` | HTTP routes |
| `envoy.config.cluster.v3.Cluster` | upstream clusters |
| `envoy.extensions.transport_sockets.tls.v3` | TLS context |
| `envoy.config.bootstrap.v3.Bootstrap` | bootstrap config |

The v3 API is mandatory since 1.18; v2 is removed.

References: `https://www.envoyproxy.io/docs/envoy/latest/configuration/configuration`.

## Gateway API

Envoy is a reference implementation of the Kubernetes Gateway API:

- `GatewayClass`, `Gateway`, `HTTPRoute`, `TCPRoute`.
- Gateway API ≥ v1.0 (since 2023).
- Compatible with `envoy-gateway`, `contour`, `istio`, etc.

References: `https://gateway-api.sigs.k8s.io/`.

## Filter chain

| Filter | Use |
|---|---|
| `envoy.filters.network.http_connection_manager` | HTTP handling |
| `envoy.filters.http.router` | routing |
| `envoy.filters.http.lua` | scripting |
| `envoy.filters.http.ratelimit` | rate limiting |
| `envoy.filters.http.ext_authz` | external authorization |
| `envoy.filters.http.jwt_authn` | JWT validation |
| `envoy.filters.network.tcp_proxy` | L4 proxy |

## TLS

- `transport_socket` with `envoy.transport_sockets.tls` context.
- `common_tls_context.tls_certificate_sds_secret_configs` for SDS.
- HTTP/2 ALPN: `h2`.
- HTTP/1.1 fallback.

## Observability

| Feature | Use |
|---|---|
| Access logs | JSON, configurable |
| Stats | Prometheus integration |
| Tracing | OpenTelemetry, Zipkin |
| Tap | on-the-wire capture |

References: `https://www.envoyproxy.io/docs/envoy/latest/operations/`.

## Cross-reference

| Domain | Card |
|---|---|
| Istio | `ISTIO_VERSION_GOVERNANCE.md` |
| Kubernetes | `KUBERNETES_VERSION_GOVERNANCE.md` |
| HTTP/3 | `HTTP_3_RFC_9114_VERSION_GOVERNANCE.md` |
| OPA | `OPA_VERSION_GOVERNANCE.md` |

## Sources

- Envoy documentation: `https://www.envoyproxy.io/docs/envoy/latest/`
- Envoy releases: `https://github.com/envoyproxy/envoy/releases`
- Envoy quickstart: `https://www.envoyproxy.io/docs/envoy/latest/start/quick-start/`
- Gateway API: `https://gateway-api.sigs.k8s.io/`
