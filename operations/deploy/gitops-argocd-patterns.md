# gitops-argocd-patterns

**Issue:** Production patterns for Argo CD application delivery and multi-cluster management
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Argo CD is the most widely adopted GitOps controller. Teams need consistent patterns for app-of-apps structure, RBAC, sync policies, and multi-cluster promotion.

## Pattern / Solution
App-of-apps pattern:
```yaml
# root-app.yaml — one Application that manages all other Applications
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/my-org/fleet
    targetRevision: main
    path: apps/production
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

ApplicationSet for multi-cluster promotion:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: guestbook
spec:
  generators:
  - list:
      elements:
      - cluster: staging
        url: https://staging.k8s.example.com
      - cluster: production
        url: https://prod.k8s.example.com
  template:
    metadata:
      name: '{{cluster}}-guestbook'
    spec:
      project: default
      source:
        repoURL: https://github.com/my-org/guestbook
        targetRevision: main
        path: 'overlays/{{cluster}}'
      destination:
        server: '{{url}}'
        namespace: guestbook
```

Sync waves for ordered rollout:
```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"   # lower = earlier
```

Diff from CLI:
```bash
argocd app diff my-app --local ./manifests
argocd app sync my-app --dry-run
argocd app sync my-app --strategy=hook
```

## Gotchas
- `selfHeal: true` will revert any manual `kubectl` changes — document this for on-call engineers
- Sync waves pause between waves only when health checks pass; mis-configured probes cause stalls
- `argocd app delete` with `--cascade` deletes the live resources, not just the Application object
- Store `argocd-secret` (admin password, webhook secret) in a secrets manager, not Git
- ApplicationSets with `preserveResourcesOnDeletion: false` will nuke live resources if the generator entry is removed

## Related
- `gitops-flux-cd.md`
- `gitops.md`
- `argo-rollouts-2026.md`
- `multi-region-deployment.md`
