# CNCF Flux GitOps Reconciliation Governance

## Purpose

Govern the use of Flux as the GitOps reconciliation engine so that Git remains the sole interface for declaring cluster state, reconciliation loops are tuned to catch drift quickly, and secret/dependency ordering is explicit rather than discovered during an incident.

## Scope

Applies to every Flux-managed cluster and repository the studio operates: source controllers, kustomizations, helm releases, and image automation. It does not cover Argo CD usage (covered separately) or application delivery strategies.

## Workflow

1. Declare all cluster state through Git: kustomizations, Helm releases, and sources are versioned artifacts; imperative `kubectl apply` to Flux-managed namespaces is prohibited outside break-glass.
2. Structure reconciliation ordering explicitly: `dependsOn` between kustomizations where CRDs, namespaces, or cert-manager resources must exist before consumers reconcile; implicit ordering by apply luck is prohibited.
3. Tune reconciliation intervals deliberately: source refresh and reconciliation intervals chosen per environment (faster in dev, stable in prod), with the rationale recorded.
4. Run secret delivery through the designated mechanism (e.g., sealed secrets or external secrets operator); plaintext secrets in Git are prohibited, and sealed-secret templates live beside the workloads they serve.
5. Automate image updates with image automation controllers bounded by tag filters and update policies; automation that can bump a chart pinned by digest is disabled.
6. Alert on reconciliation failures and drift events: a kustomization failing health checks must page, and suspension of reconciliation (`spec.suspend`) is a recorded, time-boxed intervention.
7. Bootstrap and upgrade Flux deliberately: pin the Flux version per cluster fleet, test upgrades on a canary cluster before fleet promotion.

## Controls and evidence

- Repository structure documentation with kustomization dependency graph.
- Reconciliation interval configuration per environment with rationale.
- Sealed/external secrets usage records and a confirmation that no plaintext secrets exist in Git history.
- Alerting configuration for reconciliation failure and health-check failure.
- Flux version pinning record and canary upgrade history.

## Validation

- Confirm no kustomization or helm release exists in a Flux-managed cluster without a corresponding Git source.
- Sample the dependency graph and confirm `dependsOn` covers all orderings that previously failed on cold boot.
- Confirm a forced drift event (manual edit in cluster) is reverted by reconciliation within the configured interval.

## Failure correction

- **Drift not reverted** → check suspension status and interval config; unsuspend or correct, and record why drift persisted.
- **Cold-boot ordering failure** → add the missing `dependsOn` and reproduce the cold boot in a test cluster.
- **Plaintext secret committed** → purge history, rotate the credential, and review the secret-handling control that failed.

## Limitations

- Reconciliation reverts drift but does not explain it; pair with audit logging to attribute manual changes.
- Image automation trades control for freshness; policy bounds must be explicit to avoid unwanted major-version drift.
- Flux and Argo CD in one cluster can fight over resources; scope each to disjoint namespaces deliberately.

## Scope note

This article is part of the operations leaf and pairs with Argo CD guidance and sealed-secrets practices. Cross-reference: `deploy/argo-cd-gitops-getting-started.md`, `deploy/argocd-sync-window-enforcement-tests.md`, and `monitoring/README.md`.

## Canonical sources

- Flux Documentation — Get Started: https://fluxcd.io/flux/get-started/
- Flux Documentation — Kustomization Controller: https://fluxcd.io/flux/components/kustomize/
- Flux Documentation — Image Automation: https://fluxcd.io/flux/guides/image-update/
- OpenGitOps — Principles: https://opengitops.dev/
- Kubernetes Documentation — Declarative configuration: https://kubernetes.io/docs/concepts/overview/working-with-objects/kubernetes-objects/
