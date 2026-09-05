---
title: Open Policy Agent (OPA / Rego) Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Open Policy Agent; CNCF; Styra; OPA documentation at openpolicyagent.org
---

# Open Policy Agent (OPA / Rego) Version Governance

## Scope

This card governs how `orchords-docs` evaluates the Open Policy Agent (OPA) and the Rego policy language across versions, runtime modes, and integration patterns. It is the reference input for any KB card that touches admission control, authorization, or policy-as-code.

## Why this card exists

OPA has graduated from CNCF (March 2021) and is the de-facto standard for policy-as-code across Kubernetes, microservices, and API gateways. Without an explicit card, the KB cites Rego versions and integration patterns that ignore v0.x vs v1.x and `rego.v1` migration.

## Versions

OPA 0.x series:

- 0.10–0.20 — early adoption.
- 0.30–0.40 — Kubernetes admission (kube-mgmt).
- 0.50–0.60 — multi-cloud (AWS, GCP, Azure).
- 0.65–0.69 — last 0.x series.

OPA 1.x series (current):

- 1.0 (stable, Rego v1 introduced).
- 1.1–1.4 — incremental.

References: `https://github.com/open-policy-agent/opa/releases`.

## Rego language

Rego is the policy language:

- **rego.v0** — classic syntax (`if` blocks).
- **rego.v1** — current syntax (`if` → `if { ... }`).

References: `https://www.openpolicyagent.org/docs/latest/policy-language/`.

## Runtime modes

| Mode | Use |
|---|---|
| Library | embedded in Go services via SDK |
| CLI | `opa eval`, `opa test`, `opa fmt` |
| Server | HTTP API for policy evaluation |
| Bundle | distribution of policy + data |

References: `https://www.openpolicyagent.org/docs/latest/`.

## Integration patterns

| Integration | Use |
|---|---|
| Kubernetes admission (Gatekeeper / kube-mgmt) | cluster-scoped admission |
| Istio / Envoy (OPA WASM) | service-mesh authorization |
| API gateways (Kong, Tyk, Envoy) | API authorization |
| Microservices (SDK) | embedded authorization |
| CI/CD (conftest) | policy check on manifests |

## Bundle distribution

OPA bundles:

- `.tar.gz` of `policy.tar` + `data.json` + `.manifest`.
- Signed via `cosign` or GPG.
- Pulled by OPA server / agent on a refresh interval.

References: `https://www.openpolicyagent.org/docs/latest/management-bundles/`.

## Decision logging

OPA emits decision logs:

- `decision_id`, `input`, `result`, `path`, `timestamp`.
- Stream to stdout, file, or HTTP webhook.
- Required for audit and observability.

References: `https://www.openpolicyagent.org/docs/latest/decision-log/`.

## Cross-reference

| Domain | Card |
|---|---|
| Kubernetes | `KUBERNETES_VERSION_GOVERNANCE.md` |
| Istio | `ISTIO_VERSION_GOVERNANCE.md` |
| Service mesh | `ISTIO_VERSION_GOVERNANCE.md` |
| Admission | (deferred) |

## Sources

- OPA documentation: `https://www.openpolicyagent.org/docs/latest/`
- OPA releases: `https://github.com/open-policy-agent/opa/releases`
- Rego playground: `https://play.openpolicyagent.org/`
- Styra: `https://www.styra.com/`
- CNCF OPA: `https://www.cncf.io/projects/open-policy-agent-opa/`
