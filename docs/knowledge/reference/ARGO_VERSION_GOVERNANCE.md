---
title: Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Argo Project; CNCF Argo Workflows, Argo CD, Argo Events, Argo Rollouts
---

# Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance

## Scope

This card governs how `orchords-docs` evaluates the Argo project family across versions, CRD APIs, and deployment patterns.

## Why this card exists

Argo is the canonical Kubernetes-native workflow and deployment toolkit. Without an explicit card, the KB cites Argo practices that ignore the four-project split (Workflows, CD, Events, Rollouts), version skew rules, and ArgoCD Application / ApplicationSet APIs.

## Argo Workflows

Workflows is the canonical Kubernetes-native workflow engine:

| Version | Status |
|---|---|
| 3.4–3.5 | legacy |
| 3.6 | current LTS |
| 3.7 | current |

References: `https://github.com/argoproj/argo-workflows/releases`.

CRD API: `argoproj.io/v1alpha1` (stable for years).

## Argo CD

Argo CD is the canonical GitOps controller (per `GITOPS_VERSION_GOVERNANCE.md`).

| Version | Status |
|---|---|
| 2.4–2.6 | legacy |
| 2.7–2.10 | current |
| 2.11+ | current |

CRD API: `argoproj.io/v1alpha1`.

References: `https://github.com/argoproj/argo-cd/releases`.

## Argo Events

Argo Events is the event-driven workflow trigger:

| Version | Status |
|---|---|
| 1.7–1.8 | legacy |
| 1.9+ | current |

References: `https://github.com/argoproj/argo-events/releases`.

## Argo Rollouts

Argo Rollouts is the progressive-delivery controller:

| Version | Status |
|---|---|
| 1.5–1.6 | legacy |
| 1.7+ | current |

Strategies: BlueGreen, Canary, canary with analysis.

References: `https://github.com/argoproj/argo-rollouts/releases`.

## Cross-project compatibility

Argo components version-skew rules:

- Argo Workflows and Argo Events: aligned minor versions.
- Argo CD: independent.
- Argo Rollouts: independent.

## Cross-reference

| Domain | Card |
|---|---|
| GitOps | `GITOPS_VERSION_GOVERNANCE.md` |
| Kubernetes | `KUBERNETES_VERSION_GOVERNANCE.md` |

## Sources

- Argo Workflows: `https://github.com/argoproj/argo-workflows`
- Argo CD: `https://github.com/argoproj/argo-cd`
- Argo Events: `https://github.com/argoproj/argo-events`
- Argo Rollouts: `https://github.com/argoproj/argo-rollouts`
- CNCF Argo: `https://www.cncf.io/projects/argo/`
