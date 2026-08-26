# gitops

**Issue:** GitOps — declarative, Git as source of truth
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy to production. You SSH into a server. You
run a command. The next person doesn't know what you
did. The environment drifts.

## Root cause
**Without GitOps, deployments are manual + drift.** Use
GitOps.

**Source:** Weaveworks — GitOps.

## The "GitOps" concept

GitOps:
- **Git:** Source of truth
- **Declarative:** Config as code
- **Pulled:** Operators pull from Git
- **Synced:** Continuous sync

The environment is a function of Git.

## The "declarative config" pattern

For declarative config:
```yaml
# deployments/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml

# deployments/production/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: my-app
          image: my-app:1.2.3
```

The config is declarative.

## The "Argo CD" pattern

For Argo CD:
```yaml
# argocd-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/myorg/myrepo
    targetRevision: HEAD
    path: deployments/production
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

Argo CD syncs from Git.

**Source:** Argo CD:
https://argo-cd.readthedocs.io/

## The "Flux" pattern

For Flux:
```yaml
# flux-system/gotk-sync.yaml
apiVersion: source.toolkit.fluxcd.io/v1beta2
kind: GitRepository
metadata:
  name: my-app
  namespace: flux-system
spec:
  interval: 1m
  ref:
    branch: main
  url: https://github.com/myorg/myrepo
```

Flux syncs from Git.

**Source:** Flux:
https://fluxcd.io/

## The "drift detection" pattern

For drift detection:
- **Argo CD:** Shows "OutOfSync" status
- **Flux:** Reconciliation loops
- **Polaris:** Audit + recommendations

```ts
// Argo CD will detect:
// - Manual change to a deployment
// - Status: OutOfSync
// - Auto-sync: will revert
```

The drift is detected.

## The "sealed secrets" pattern

For sealed secrets:
```bash
# Encrypt a secret
kubeseal --controller-namespace=sealed-secrets < secret.yaml > sealed-secret.yaml

# Commit to Git
git add sealed-secret.yaml
```

The secret is encrypted.

**Source:** Sealed Secrets:
https://github.com/bitnami-labs/sealed-secrets

## The "environment promotion" pattern

For promotion:
```
dev (auto-deploy on merge)
  ↓
staging (auto-deploy on merge)
  ↓
production (manual approval + auto-deploy)
```

The environments are promoted.

## The "preview environments" pattern

For preview, per PR:
```yaml
# argocd-app-preview.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app-pr-123
spec:
  source:
    repoURL: https://github.com/myorg/myrepo
    targetRevision: pull/123/head
```

The preview is per PR.

## The "rollback" pattern

For rollback:
- **Git revert:** Revert the commit
- **Sync:** Argo CD / Flux syncs
- **Done:** Old version is live

```bash
git revert <commit>
git push
```

The rollback is via Git.

## The "GitOps observability" pattern

For observability:
- **Sync status:** In sync / out of sync
- **Drift count:** How many resources drifted
- **Last sync:** When was the last sync
- **Health:** Healthy / degraded

```ts
metrics.gauge('gitops.drift_count', driftCount);
metrics.gauge('gitops.last_sync_timestamp', lastSync);
```

The GitOps is monitored.

## The "GitOps anti-pattern" anti-patterns

### 1. Manual deploys
- **Issue:** Drift
- **Fix:** GitOps

### 2. Secrets in plain
- **Issue:** Leak
- **Fix:** Sealed secrets

### 3. No drift detection
- **Issue:** Manual changes persist
- **Fix:** Continuous sync

### 4. No rollback
- **Issue:** Hard to undo
- **Fix:** Git revert + sync

## Verification
- **Test:** Sync works
- **Test:** Drift is detected
- **Test:** Rollback works
- **Live:** Sync status is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "manual deploys" anti-pattern.** Use GitOps.
- **The "secrets in plain" anti-pattern.** Sealed
  secrets.
- **The "no drift detection" anti-pattern.** Continuous
  sync.

## Related
- `preview-environments.md`
- `env-binding-precedence.md`
- `zero-downtime-deploys.md`
- `feature-environment-promotion.md`
- `safe-deploy-checklist.md`
- Weaveworks: https://www.weave.works/technologies/gitops/
- Argo CD: https://argo-cd.readthedocs.io/
- Flux: https://fluxcd.io/
