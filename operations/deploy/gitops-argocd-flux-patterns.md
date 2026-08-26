# GitOps — ArgoCD, Flux, and Kubernetes Deployment Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Kubernetes deployments are triggered by CI pipelines that `kubectl
apply` manifests directly. There is no single source of truth for what
is running in the cluster — engineers compare manifests across repos,
Helm release versions, and cluster state to understand the current
deployment. Drift occurs when someone runs `kubectl edit` in production.
Rollbacks require finding the previous CI run and re-triggering it. You
have no audit trail of what changed, when, and who approved it.

## Context

GitOps uses Git as the single source of truth for declarative
infrastructure and applications. A GitOps controller (ArgoCD or Flux)
running inside the cluster continuously reconciles the actual cluster
state with the desired state defined in Git. Any divergence is
automatically detected and corrected. In 2026, GitOps is the industry
standard for Kubernetes deployment, with ArgoCD and Flux as the two
CNCF-graduated tools. ArgoCD provides a centralized management plane
with a built-in UI, RBAC, and the app-of-apps pattern. Flux follows a
Kubernetes-native, CRD-based, decentralized model with no central UI.

## ArgoCD vs. Flux

| Feature | ArgoCD | Flux |
|---|---|---|
| Architecture | Centralized server + UI | Decentralized CRDs |
| UI | Built-in web dashboard | No built-in UI (Weave GitOps optional) |
| RBAC | Built-in, project-scoped | Kubernetes-native RBAC |
| Multi-cluster | App of apps, ApplicationSets | Kustomization across clusters |
| Helm support | Helm charts as Applications | HelmRelease CRD |
| Image automation | External (Argo Image Updater) | Built-in Image Automation controller |
| Secrets | External (SOPS, Sealed Secrets) | Native SOPS decryption |
| Drift detection | UI shows diff, auto-sync optional | Auto-reconciliation default |
| Best for | Platform teams, multi-tenant | Developer self-service, Kubernetes-native |

## ArgoCD setup

### Application definition

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api-server
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/k8s-manifests
    targetRevision: main
    path: apps/api-server/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: true        # Delete resources removed from Git
      selfHeal: true     # Revert manual cluster changes
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 3
      backoff:
        duration: 5s
        maxDuration: 3m
```

### App of apps (multi-application management)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/org/k8s-manifests
    path: argocd-apps   # Directory of Application manifests
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### ApplicationSet (dynamic generation)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: microservices
  namespace: argocd
spec:
  generators:
    - git:
        repoURL: https://github.com/org/k8s-manifests
        directories:
          - path: apps/*
  template:
    metadata:
      name: '{{path.basename}}'
    spec:
      source:
        repoURL: https://github.com/org/k8s-manifests
        path: '{{path}}/overlays/production'
      destination:
        server: https://kubernetes.default.svc
        namespace: production
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

## Flux setup

### GitRepository and Kustomization

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: k8s-manifests
  namespace: flux-system
spec:
  interval: 1m
  url: https://github.com/org/k8s-manifests
  ref:
    branch: main
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: api-server
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: k8s-manifests
  path: ./apps/api-server/overlays/production
  prune: true
  force: false
  targetNamespace: production
```

### Flux HelmRelease

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: redis
  namespace: production
spec:
  interval: 10m
  chart:
    spec:
      chart: redis
      version: "18.x"
      sourceRef:
        kind: HelmRepository
        name: bitnami
        namespace: flux-system
  values:
    architecture: standalone
    auth:
      enabled: true
      existingSecret: redis-credentials
```

### Flux image automation

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: api-server
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: api-server
  policy:
    semver:
      range: ">=1.0.0"
---
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageUpdateAutomation
metadata:
  name: auto-update
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: k8s-manifests
  git:
    checkout:
      ref:
        branch: main
    commit:
      author:
        email: flux@example.com
        name: Flux
      messageTemplate: "Update image to {{.NewTag}}"
    push:
      branch: main
```

## Repository strategies

```
1. Mono-repo (app code + manifests):
   → Simple for small teams
   → CI builds trigger deployment automatically
   → Risk: any code change triggers sync

2. Separate config repo (recommended):
   → App repo: source code + Dockerfile
   → Config repo: Kubernetes manifests
   → CI updates image tag in config repo
   → GitOps controller syncs config repo only
   → Clean audit trail: every deployment is a Git commit

3. Hybrid (ArgoCD + Flux):
   → Flux for infrastructure (cluster addons, CNI, CRDs)
   → ArgoCD for applications (developer-facing, UI)
   → Leverages each tool's strengths
```

## Anti-patterns

- **CI-triggered kubectl apply** — pushing manifests from CI bypasses
  the GitOps controller, creating state that Git does not know about.
  The controller will revert the change on next reconciliation. All
  changes must go through Git.
- **Disabling self-heal** — turning off automatic drift remediation
  because "someone might need to make manual changes." This defeats
  the purpose of GitOps. Use the Git workflow for all changes; if
  emergency changes are needed, commit them to Git immediately.
- **Storing secrets in Git** — committing unencrypted secrets to the
  Git repository. Use SOPS, Sealed Secrets, or External Secrets
  Operator to encrypt secrets before committing.
- **One Application per resource** — creating an ArgoCD Application
  for every individual Kubernetes resource. Group related resources
  into Applications by bounded context or service.

## Gotchas

- **Helm hooks** — ArgoCD and Flux handle Helm hooks differently.
  ArgoCD translates hooks to Argo sync hooks; Flux runs them natively.
  Test hook behavior in your specific GitOps tool.
- **CRD ordering** — CRDs must be applied before resources that use
  them. Both ArgoCD and Flux support sync waves / dependency ordering,
  but misconfigured ordering causes failed syncs.
- **Large repositories** — GitOps controllers poll Git repositories
  on an interval. Very large repositories (>1GB) slow down the poll
  cycle. Use sparse checkout or split repositories.
- **Reconciliation lag** — there is always a delay between Git commit
  and cluster state update (sync interval + apply time). For latency-
  sensitive deployments, trigger a manual sync or reduce the interval.

## Verification

- All deployments are driven by Git commits (no direct kubectl apply).
- GitOps controller runs with selfHeal/prune enabled.
- Drift is automatically detected and corrected.
- Secrets are encrypted before committing to Git.
- Rollback is a `git revert` commit.
- Multi-cluster deployments use ApplicationSets or Kustomizations.
- Audit trail exists for every deployment (Git log).

## Related

- `documentation/categories/deploy/progressive-canary-deployment-rollback.md`
- `documentation/categories/deploy/infrastructure-drift-detection-remediation.md`
- `documentation/categories/infra/kubernetes-autoscaling-hpa-keda.md`

## Source URLs (verified 2026-08-16)

- GitOps with ArgoCD and Flux Kubernetes Guide 2026 — https://devstarsj.github.io/2026/03/18/gitops-argocd-flux-kubernetes-guide-2026/
- GitOps 2026: ArgoCD vs Flux Definitive Comparison — https://devstarsj.github.io/devops/kubernetes/gitops/2026/05/25/gitops-argocd-vs-flux-kubernetes-cd-comparison-2026/
- GitOps Advanced Patterns with Flux and ArgoCD 2026 — https://devstarsj.github.io/2026/06/20/gitops-advanced-patterns-flux-argocd-2026/
- ArgoCD vs Flux: We Run Both in Production 2026 — https://tasrieit.com/blog/argocd-vs-flux-gitops-comparison-2026
