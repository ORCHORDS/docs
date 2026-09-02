# CNCF Argo CD ApplicationSet Multi-Tenant Governance

## Purpose

Govern the use of Argo CD ApplicationSets so that fleet-scale GitOps — one generator definition producing many applications across clusters, namespaces, or tenants — stays intentional: tenant isolation deliberate, template parameters controlled, and blast radius of a single ApplicationSet change understood before it is merged.

## Scope

Applies to every ApplicationSet used by the studio across clusters and environments. It covers generator selection, template hygiene, multi-tenancy isolation, and drift handling for generated applications. It does not cover single-application Argo CD patterns (covered by the Argo CD progression guidance) or workload cluster design.

## Workflow

1. Select the generator type (git, cluster, list, matrix, merge, pull request, SCM provider) to match the actual source of truth for "what should exist"; document why the generator fits.
2. Treat ApplicationSet templates as privileged code: changes that alter namespaces, destinations, or RBAC-relevant fields require review by the platform owners, not just the requesting team.
3. Isolate tenants with the ApplicationSet's own scoping — each tenant's applications generate within their namespaces and target only their permitted clusters; cross-tenant destinations in one ApplicationSet are prohibited.
4. Control template parameter injection: restrict which fields external generators (e.g., PR generators) can influence; user-controllable PR labels must not reach destinations, namespaces, or sync options.
5. Prefer progressive rollout of fleet-wide changes: sync waves, stages, or environment-ordered generators over "update all clusters simultaneously."
6. Monitor generated application health as a fleet: alert on per-cluster sync failures that a fleet-wide change induces, and roll back at the ApplicationSet level rather than hand-patching generated applications.
7. Audit generated applications periodically: the set of applications an ApplicationSet produces must match the inventory the generators logically imply; orphaned generated applications are removed deliberately.

## Controls and evidence

- ApplicationSet definitions in version control with review records for RBAC-affecting changes.
- Generator selection rationale per ApplicationSet.
- Parameter allowlist for externally influenced fields (PR title, labels) with tests proving restricted fields cannot be injected.
- Fleet sync dashboards with per-cluster failure alerting.
- Generated-application audit results showing reconciliation with generator-implied inventory.

## Validation

- Sample one externally-parameterized ApplicationSet and confirm attempts to inject destinations or namespaces through external fields fail.
- Confirm each tenant's generated applications target only permitted namespaces and clusters.
- Confirm a recent fleet-wide change used progressive rollout or documents why simultaneous rollout was acceptable.

## Failure correction

- **External parameter injection attempt succeeded** → treat as a security finding: fix the template, audit generated applications for contamination, and rotate any exposed credentials.
- **Fleet-wide change caused multi-cluster sync failures** → roll back the ApplicationSet revision, then re-introduce with staged rollout.
- **Orphaned generated applications accumulating** → reconcile the generator or prune policy deliberately; do not hand-delete without recording why.

## Limitations

- ApplicationSets amplify a single definition's blast radius; the governance here reduces but does not eliminate fleet-wide failure risk.
- Generator capabilities differ across Argo CD versions; consult version-specific docs before relying on newer generators.
- Multi-tenancy at the ApplicationSet layer does not replace namespace RBAC and cluster-level policy enforcement.

## Scope note

This article is part of the operations leaf and builds on Argo CD progression guidance. Cross-reference: `deploy/argo-cd-app-of-apps-progression.md`, `deploy/argocd-sync-window-enforcement-tests.md`, and `deploy/argo-rollouts-canary-metric-analysis.md`.

## Canonical sources

- Argo CD Documentation — ApplicationSet: https://argo-cd.readthedocs.io/en/stable/user-guide/application-set/
- Argo CD Documentation — Generators: https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators/
- Argo CD — Security considerations: https://argo-cd.readthedocs.io/en/stable/security/
- Kubernetes Documentation — API Server Access Control: https://kubernetes.io/docs/concepts/security/controlling-access/
- SLSA v1.0 — Supply-chain Levels for Software Artifacts: https://slsa.dev/
