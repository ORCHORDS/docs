# gitops-argocd-flux-2026

**Issue:** A platform team moves from `kubectl apply` in CI pipelines to GitOps. The team reads about ArgoCD and Flux. Both are CNCF Graduated, both pull-based, both reconcile. The team needs the 2026 decision framework for which to pick.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

GitOps is the 2026 default for Kubernetes deployments. The 4 OpenGitOps principles (declarative, versioned/immutable, pulled automatically, continuously reconciled) are mature and proven. Two CNCF Graduated tools implement them: ArgoCD (rich UI, application-centric) and Flux (controller-based, Kubernetes-native). Both work; the question is which fits the team.

## Root cause

ArgoCD centralizes control plane + UI + per-application RBAC. Flux decentralizes into composable controllers with built-in image automation. The "AWS in Plain English" 2026 framing: "Argo CD is a product for your developers; Flux is an engine for your platform."

## The 4 OpenGitOps principles

1. **Declarative.** Desired state as Kubernetes manifests, Helm values, Kustomize overlays.
2. **Versioned and immutable.** Git is the single source of truth.
3. **Pulled automatically.** In-cluster agent watches Git, fetches, applies. CI never touches the cluster.
4. **Continuously reconciled.** Drift detected and corrected on the reconcile loop.

## The 9-axis comparison (June 2026)

| Axis | Argo CD | Flux |
|---|---|---|
| Version | v3.4.3 (May 28, 2026) | v2.8.8 (May 20, 2026) |
| GitHub stars | ~23,100 | ~8,180 (flux2) |
| Architecture | Centralized control plane | Modular GitOps Toolkit |
| Native web UI | Full-featured dashboard | None (Weave GitOps, Grafana) |
| Multi-cluster | Native hub-spoke, ApplicationSets | Each cluster runs own Flux, coordination via Git |
| Image automation | ArgoCD Image Updater (separate) | Built-in (2 controllers) |
| Secrets | External Secrets Operator / Vault | Native SOPS integration |
| Progressive delivery | Argo Rollouts (separate) | Flagger (separate) |
| Resource footprint | Higher (API + UI + controller + Redis) | Lower (lightweight static binary controllers) |
| Air-gapped | Supported | Strong, designed for it |

## The 5 decision rules

1. **Developers need self-service visibility and SSO** → Argo CD. UI pays for the heavier footprint.
2. **Many clusters, lean footprint, machine-native operation** → Flux. Controllers disappear into the cluster.
3. **Image automation is critical** → Flux (built-in) wins over ArgoCD Image Updater.
4. **Helm-heavy stack** → both work; Flux's Helm Controller is purpose-built.
5. **Both** → documented pattern of Flux for infrastructure, Argo CD for application visibility.

## The 5 production best practices

1. **One repo, one cluster, one tool to start.** Add complexity (multi-cluster, multi-tenant, progressive delivery) only when you understand why you need it.
2. **External Secrets Operator for secrets** - never commit secrets, even encrypted, unless you use SOPS with proper key management.
3. **Application code and Kubernetes manifests in separate repos.** CI updates manifest repo, GitOps reconciles from it.
4. **Use ApplicationSet (Argo) or Kustomization+Repository structure (Flux)** to scale to dozens of clusters.
5. **Wire progressive delivery** (Argo Rollouts or Flagger) for canary/blue-green when downtime costs real money.

## The 5 anti-patterns

1. **Putting secrets in Git, even encrypted.** SOPS + key management or ESO only.
2. **kubectl apply in CI.** Defeats the pull model; CI should not have cluster access.
3. **Monolithic app-of-apps** with hundreds of applications in one file. Use ApplicationSet templates.
4. **No drift detection alert.** Configure notifications (Argo Notifications, Flux notification-controller) for `Status: Degraded`.
5. **Auto-sync to production without approval gates.** Use Sync Waves + manual approval for production.

## The 5-step adoption pattern

1. **Pick the tool** based on team profile (UI vs engine).
2. **Bootstrap one cluster** with the basic GitOps pipeline.
3. **Migrate one app** end-to-end (manifest repo + sync to cluster + verify).
4. **Add ApplicationSet/Kustomization template** for the next 10 apps.
5. **Wire notifications, image automation, progressive delivery** once the basic loop is proven.

## The 4 architecture patterns

1. **Repo-per-cluster** (clusters/production/, clusters/staging/) with Flux per cluster.
2. **App-of-apps** (Argo) - top-level app with child apps templated.
3. **ApplicationSet generators** (Argo) - matrix generators from cluster list, file lists.
4. **Mono-repo per org** with overlays (Kustomize) per environment.

## Verification

The tell that GitOps is set up right:

- CI never touches the cluster; only the in-cluster agent has credentials
- Drift detected within minutes; auto-corrected if `selfHeal: true`
- New cluster bootstraps from one command
- Manifest promotion is a PR (not a pipeline action)
- Notifications fire on `Degraded` status

The tell it isn't:

- CI has `kubectl` credentials
- "We push manifests from CI" (push model, not pull)
- Manual reconciliation runs as cron
- Production changes bypass Git

## Gotchas

- **ArgoCD consumes ~2x the CPU/memory of Flux** during initial sync. Steady-state gap narrows.
- **Flux multitenancy** is per-cluster; coordination is via Git structure, not central control plane.
- **ApplicationSet generators** are powerful but can mask drift if not configured to detect cluster removals.
- **Air-gapped installs:** both support; Flux is more documented.
- **SOPS key management** is the failure point for most teams. Use age or KMS-backed keys, not literal GPG.

## Related

- `worktree/release-please-semantic-release.md` - version automation
- `worktree/branch-strategies-2026.md` - branch flow
- `deploy/feature-rollout-strategies.md` - if exists in repo

## Source URLs (verified 2026-08-10)

- https://devstarsj.github.io/2026/02/20/gitops-argocd-flux-production-guide/
- https://devstarsj.github.io/2026/03/18/gitops-argocd-flux-kubernetes-guide-2026/
- https://lenshq.io/blog/gitops-argocd-flux
- https://tasrieit.com/blog/argocd-vs-flux-gitops-comparison-2026
- https://tech-insider.org/argocd-vs-flux-2026/
- https://opengitops.dev/
