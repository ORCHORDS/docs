# CNCF Argo Rollouts Progressive Governance

## Purpose

Argo Rollouts (CNCF Incubating) is a Kubernetes controller that provides advanced deployment strategies (canary, blue-green, A/B testing, traffic mirroring) as a superset of Deployments. The progressive-delivery governance pattern captures the rollout strategy, the traffic-routing mechanism (NGINX, Istio, AWS ALB, SMI, Traefik), the metric-driven analysis (Prometheus, Datadog, Kayenta), and the rollback procedure. Without explicit governance, rollouts drift from `Deployment` to `Rollout` inconsistently and the analysis-templated promotion becomes a manual step.

## Current context and source status

Argo Rollouts 1.7 (released 2024) and Argo Rollouts 1.8 (released 2025) are the current supported versions. Argo Rollouts 1.9 entered beta in 2026. The project follows the CNCF Incubating governance model.

## Governance pattern

1. Inventory every Rollout with strategy, traffic router, and analysis template.
2. Pin Argo Rollouts version and CRD version in cluster bootstrap.
3. Define the rollout strategy per workload: canary, blue-green, or A/B testing.
4. Define the traffic router (NGINX, Istio, AWS ALB, SMI, Traefik, Ambassador) per workload.
5. Configure analysis templates with Prometheus queries for success rate, latency, and error rate.
6. Set promotion policy: auto-promote on analysis success, auto-abort on analysis failure.
7. Define the canary steps: traffic percentage and pause duration per step.
8. Monitor rollout metrics: `argo_rollouts_*` metrics including `rollouts_analysis_run_status`.
9. Document the manual abort procedure for incidents.
10. Maintain a documented rollback: `kubectl argo rollouts abort` or `kubectl argo rollouts undo`.
11. Reconcile Rollouts with Deployments; convert Deployments to Rollouts as a one-time migration with documented strategy.

## Validation and evidence

- Argo Rollouts version and CRD version recorded in cluster inventory.
- Rollout strategy and traffic router recorded per workload.
- Analysis templates committed to GitOps.
- Auto-promote / auto-abort configured and tested.
- Metrics dashboard deployed.
- Rollback procedure tested in staging.

## Failure correction

Common defects include missing analysis template (rollout hangs indefinitely), inconsistent traffic router between Rollout and Ingress, and missing abort procedure. Corrective actions include requiring analysis template at admission, validating traffic router consistency, and documenting abort in the runbook.

## Limitations

- Argo Rollouts is not a substitute for the Deployment controller; both can coexist (rollouts replace specific Deployments).
- Some traffic routers have limited metrics integration (validate before rollout).
- A/B testing requires header-based routing which not all routers support.
- Argo Rollouts does not migrate Deployments automatically; explicit conversion is required.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (Argo Rollouts deployment topology), **engineering** (rollout strategy design), **security** (traffic routing and authn), and **templates** (Rollout manifest template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- Argo Rollouts documentation (CNCF Incubating): https://argo-rollouts.readthedocs.io/
- Argo Rollouts GitHub repository (CNCF Incubating): https://github.com/argoproj/argo-rollouts
- Argo Rollouts analysis templates (CNCF Incubating): https://argo-rollouts.readthedocs.io/en/stable/analysis/

Sources were verified on September 1, 2026.