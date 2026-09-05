---
title: NGINX / NGINX Ingress Controller Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NGINX documentation (nginx.org); F5 NGINX; NGINX Ingress Controller (kubernetes/ingress-nginx)
---

# NGINX / NGINX Ingress Controller Version Governance

## Scope

This card governs how `orchords-docs` evaluates NGINX (open-source, F5 NGINX Plus) and the kubernetes/ingress-nginx controller across versions, modules, and configuration patterns.

## Why this card exists

NGINX is the canonical HTTP reverse proxy and the most widely deployed ingress in Kubernetes. Without an explicit card, the KB cites NGINX practices that ignore the open-core split (nginx vs NGINX Plus), ingress class collisions, and 1.25+ deprecations.

## Versions

| Version | Status |
|---|---|
| 1.18–1.21 | legacy stable |
| 1.22 | current stable (open source) |
| 1.24 | current stable |
| 1.25 | current stable |
| 1.26 | current stable |
| 1.27 | current mainline |
| Plus R30+ | enterprise |

References: `https://nginx.org/en/CHANGES`.

## Modules

| Module | Use |
|---|---|
| `ngx_http_ssl_module` | TLS |
| `ngx_http_v2_module` | HTTP/2 |
| `ngx_http_v3_module` | HTTP/3 (1.25+) |
| `ngx_http_proxy_module` | reverse proxy |
| `ngx_http_upstream_module` | upstream groups |
| `ngx_stream_*` | TCP / UDP proxy |

References: `https://nginx.org/en/docs/`.

## TLS

| Setting | Use |
|---|---|
| `ssl_protocols TLSv1.2 TLSv1.3;` | disallow 1.0 / 1.1 |
| `ssl_ciphers` | AEAD-only |
| `ssl_prefer_server_ciphers on;` | server-controlled |
| `ssl_session_cache shared:SSL:10m;` | session reuse |
| `ssl_session_tickets off;` | forward secrecy |

## HTTP/2 and HTTP/3

- HTTP/2 enabled by default since 1.25.1.
- HTTP/3 is `ngx_http_v3_module` (1.25+) — experimental, opt-in.

References: `https://nginx.org/en/docs/http/ngx_http_v3_module.html`.

## Ingress controller

NGINX Ingress Controller for Kubernetes:

- `kubernetes/ingress-nginx` (community).
- `nginxinc/kubernetes-ingress` (F5 NGINX).
- Versions follow NGINX minor releases.

Ingress API:

- `networking.k8s.io/v1` (since 1.22).
- `networking.k8s.io/v1beta1` removed in 1.22.

References: `https://kubernetes.github.io/ingress-nginx/`.

## Cross-reference

| Domain | Card |
|---|---|
| TLS | `TLS_RFC_8446_VERSION_GOVERNANCE.md` |
| HTTP/3 | `HTTP_3_RFC_9114_VERSION_GOVERNANCE.md` |
| Kubernetes | `KUBERNETES_VERSION_GOVERNANCE.md` |

## Sources

- NGINX docs: `https://nginx.org/en/docs/`
- NGINX changes: `https://nginx.org/en/CHANGES`
- ingress-nginx: `https://kubernetes.github.io/ingress-nginx/`
- F5 NGINX: `https://docs.nginx.com/`
