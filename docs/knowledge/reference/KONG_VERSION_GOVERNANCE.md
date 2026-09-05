---
title: Kong API Gateway Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Kong documentation; Kong Inc.; Kong Gateway OSS / Enterprise; Kong Konnect
---

# Kong API Gateway Version Governance

## Scope

This card governs how `orchords-docs` evaluates Kong API Gateway across versions, deployment modes (OSS / Enterprise / Konnect), and plugin patterns.

## Why this card exists

Kong is the canonical open-source API gateway, built on OpenResty (NGINX + Lua). Without an explicit card, the KB cites Kong practices that ignore the OSS / Enterprise / Konnect split, the plugin lifecycle, and the DB-less mode.

## Versions

| Version | Status |
|---|---|
| 2.x | legacy |
| 3.x | current LTS |
| 3.4–3.6 | current |
| 3.7+ | current |

References: `https://github.com/Kong/kong/releases`.

## Editions

| Edition | Use |
|---|---|
| Kong Gateway OSS | free, Apache-2.0 |
| Kong Gateway Enterprise | paid, self-hosted |
| Kong Konnect | managed SaaS control plane |

References: `https://docs.konghq.com/gateway/latest/`.

## Deployment modes

| Mode | Use |
|---|---|
| Traditional (DB) | PostgreSQL backend |
| DB-less | declarative YAML, no Postgres |
| Hybrid | control plane + data plane |

DB-less mode is preferred for GitOps-driven deployments.

References: `https://docs.konghq.com/gateway/latest/production/deployment-topologies/`.

## Plugins

| Plugin | Use |
|---|---|
| `key-auth` | API key authentication |
| `jwt` | JWT validation |
| `oauth2` | OAuth 2.0 |
| `rate-limiting` | request throttling |
| `cors` | CORS handling |
| `acl` | access control |
| `prometheus` | metrics exposure |
| `opentelemetry` | tracing |
| `correlation-id` | request tracing |
| `request-transformer` | header manipulation |

References: `https://docs.konghq.com/hub/`.

## Authentication and authorization

| Concept | Description |
|---|---|
| Consumer | API consumer (API key, JWT, OAuth) |
| Credential | auth credential per consumer |
| ACL | allow / deny by group |
| Route-level auth | per-route plugin |
| Global plugin | applied to all routes |

## Rate limiting

| Policy | Use |
|---|---|
| Local | in-memory (single-node) |
| Cluster | Redis-backed (multi-node) |
| `redis` | policy: redis |
| `local` | policy: local |

References: `https://docs.konghq.com/hub/kong-inc/rate-limiting/`.

## Cross-reference

| Domain | Card |
|---|---|
| NGINX | `NGINX_VERSION_GOVERNANCE.md` |
| Envoy | `ENVOY_VERSION_GOVERNANCE.md` |
| OAuth | `OAUTH_2_1_VERSION_GOVERNANCE.md` |

## Sources

- Kong documentation: `https://docs.konghq.com/gateway/latest/`
- Kong plugin hub: `https://docs.konghq.com/hub/`
- Kong GitHub: `https://github.com/Kong/kong`
- Kong decK: `https://docs.konghq.com/deck/latest/`
