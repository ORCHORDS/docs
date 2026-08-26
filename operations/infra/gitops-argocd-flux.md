# gitops-argocd-flux

GitOps is the 2026 default for delivering Kubernetes manifests: the desired
state lives in a Git repo, and a controller (Argo CD or Flux) continuously
reconciles the cluster toward that state. This article covers the failure
modes a dev team actually hits when adopting it.

## Symptom

- `kubectl get pods` shows an old image tag even though the PR was merged.
- Argo CD UI shows the application `OutOfSync` forever, never `Healthy`.
- Flux kustomization is stuck in `Reconciling` with no obvious error.
- A teammate ran `kubectl edit deployment` manually; 5 minutes later their
  change vanished (GitOps reconciled it away).
- `argocd app sync` returns green but the rollout is still serving old pods.

## Root Cause Patterns

1. **Manual kubectl edits** — GitOps treats Git as source of truth. Any
   out-of-band `kubectl apply`/`edit` is a drift that gets reverted.
2. **Image tag not updated in manifest repo** — CI pushes a new image but
   nobody updates the `kustomization.yaml` or `values.yaml` image tag.
3. **Sync policy without self-heal/prune** — without `syncPolicy.syncOptions:
   ["PrunePropagationPolicy=foreground"]` and `selfHeal: true`, drift stays.
4. **Reconcile loops from bad health checks** — custom Lua health check or
   Flux's `healthChecks` pointing at a resource that never reports healthy.

## Fix: Argo CD Application with self-heal

```yaml
# manifests/apps/my-app.yaml  (lives in the Git repo Argo CD watches)
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app
  namespace: argocd
spec:
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  source:
    repoURL: git@github.com:org/k8s-manifests
    targetRevision: main
    path: production/my-app
  syncPolicy:
    automated:
      prune: true          # delete resources removed from Git
      selfHeal: true       # revert manual drift automatically
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - ApplyOutOfSyncOnly=true
  revisionHistoryLimit: 10
```

## Fix: Image updater without a manual PR (Argo CD Image Updater)

```yaml
# annotations on the Deployment (or via argocd-image-updater config)
metadata:
  annotations:
    argocd-image-updater.argoproj.io/image-list: myapp=registry.io/myapp
    argocd-image-updater.argoproj.io/myapp.update-strategy: semver
    argocd-image-updater.argoproj.io/write-back-method: git
    argocd-image-updater.argoproj.io/git-branch: main
```

Image Updater opens a PR to the manifest repo with the new tag — no manual
manifest edit, and you still get a reviewable diff in Git.

## Fix: Flux Kustomization with health checks

```yaml
# clusters/production/my-app.yaml
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: app-manifests
  namespace: flux-system
spec:
  interval: 1m0s
  url: ssh://git@github.com/org/k8s-manifests
  ref:
    branch: main
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: my-app
  namespace: flux-system
spec:
  interval: 5m0s
  path: ./production/my-app
  sourceRef:
    kind: GitRepository
    name: app-manifests
  prune: true              # equivalent of Argo's prune
  wait: true               # block reconcile until resources are Ready
  timeout: 5m0s
  healthChecks:
    - apiVersion: apps/v1
      kind: Deployment
      name: my-app
      namespace: production
  postBuild:
    substitute:
      cluster_region: us-east-1
```

## Gotchas

- **Never `kubectl edit` a GitOps-managed resource.** With `selfHeal`/`prune`
  on, your change will be reverted within the reconcile interval (often 30s).
  Make the change in Git, full stop. Tell new hires this on day one.
- **`targetRevision: HEAD` is a footgun in Argo CD.** It pins to whatever HEAD
  was at app creation, not the latest commit on the default branch. Use an
  explicit branch name (`main`) or tag. Symptom: app never picks up new commits.
- **Flux's `interval` is a polling interval, not a push trigger.** If you need
  faster deploys, wire the Git provider webhook to the Flux `notification`
  controller — without it you wait up to `interval` after every push.
- **Argo CD `syncOptions: ["ApplyOutOfSyncOnly=true"]` skips prune on the first
  sync after enable.** Run one full sync manually, then it works as expected.
- **CRDs and their custom resources in the same sync can deadlock.** Argo CD
  applies them alphabetically; the CR may be applied before the CRD is
  registered. Fix: split CRDs into a separate Application that syncs first, or
  use `syncOptions: ["ServerSideApply=true"]` + `Replace=true` on the CRD.
- **Secrets in Git.** Do NOT commit plain-text Secrets. Use Sealed Secrets,
  SOPS, or External Secrets Operator backed by Vault/cloud KMS. A leaked
  SealedSecret private key compromises every secret ever sealed with it —
  rotate the key and re-seal on suspicion.
- **`revisionHistoryLimit` defaults to 10 in Argo CD.** Old revisions let you
  roll back from the UI; setting it to 0 removes the rollback button entirely.
- **Flux and Argo CD in the same namespace will fight.** They both reconcile.
  Pick one per cluster, or scope each to disjoint namespaces via RBAC.
- **Large monorepo + Argo CD `directory` option recurse slows the API server.**
  If your manifest repo is huge, use a sparse checkout or split repos.
- **Drift detection is not enforcement.** Argo CD's "refresh" shows drift in
  the UI, but without `selfHeal: true` it just stares at you. Decide
  explicitly: observe-only or enforce. Mixed signals cause incidents.

## Choose Argo CD vs Flux (2026 guidance)

- **Argo CD** — pick if you want a web UI, RBAC, SSO, and a rich diff view.
  Better for teams that need visibility and click-to-rollback.
- **Flux** — pick if you want pure CLI/Git, lower resource footprint, and
  tighter native integration with the CNCF ecosystem. Better for multi-cluster
  fleets driven entirely from a mono-repo.

Both are graduated CNCF projects in 2026. Neither is "wrong." Do not run both
on the same cluster managing the same resources.
