# Argo CD Image Updater Rollout Playbook

## Purpose

Enable Argo CD Image Updater so Application objects automatically track new container tags in their target registries with a bounded blast radius, deterministic update strategy, and notification feedback when tags are skipped.

## Audience

Platform engineers, GitOps operators, and application owners who already run Argo CD Applications and want automated image promotion with controlled rollback.

## Pre-conditions

- `docs/knowledge/reference/ARGOCD_IMAGE_UPDATER_VERSION_GOVERNANCE.md` reviewed and the Image Updater version pinned.
- An Argo CD Application exists with at least one tracked image and a known target registry (ECR, GCR, GHCR, ACR, Quay, or Docker Hub).
- Image Updater installed in the same cluster as Argo CD or in a paired cluster with API access to it.
- Registry credentials injected as Kubernetes Secrets; OIDC-based workload identity preferred where the registry supports it.
- Update strategy chosen up front (`git`, `git-tag-based`, or `dispatch`) and RBAC validated for write-back to the Git repo (deploy key or fine-scoped PAT).
- Argo CD Notifications controller installed and a notification target (Slack, Teams, or webhook) reachable.

## Procedure

### Step 1 — Install Image Updater via Helm

1. Add the Argo Helm repository and pin the chart version from `ARGOCD_IMAGE_UPDATER_VERSION_GOVERNANCE.md`.
2. Render values with `server.insecure=false`, metrics enabled, and the controller wired to the Argo CD server endpoint; set `--interval` to a value aligned with your release cadence (commonly `2m`).
3. Install with `helm install argocd-image-updater argo/argocd-image-updater -n argocd -f values.yaml`.
4. Confirm the pod is Ready and the controller logs report a successful registration against the Argo CD server.

### Step 2 — Register registry credentials as a Secret

5. Create a Kubernetes Secret per registry in the namespace where the Application lives; use a `kubernetes.io/dockerconfigjson` Secret or a plain Secret for non-Docker registries.
6. Where possible, exchange long-lived pull secrets for OIDC-issued tokens (ECR/GCR/ACR) so rotation is automatic.
7. Reference the Secret name in the Application's `argocd-image-updater.argoproj.io/image-list` annotation and the registry list Secret referenced by `--secret`.

### Step 3 — Annotate the Application

8. Add `argocd-image-updater.argoproj.io/image-list: <alias>=<registry>/<repo>:<tag-pattern>` to the Application metadata.
9. Add `argocd-image-updater.argoproj.io/secret: <pull-secret-name>` and, if relevant, `argocd-image-updater.argoproj.io/allow-tags: <pattern>` and `argocd-image-updater.argoproj.io/write-back-method: git`.
10. Validate with `kubectl logs deploy/argocd-image-updater | grep <app-namespace>/<app-name>` and confirm the controller parsed the annotation set without errors.

### Step 4 — Choose the update strategy

11. Pick `git` when the Git repo is the source of truth; pick `git-tag-based` when CI emits immutable tags and Image Updater should only update a tracking file or branch.
12. Pick `dispatch` when there is no Git write-back path and the controller should call the Argo CD API to trigger a Sync instead of committing.
13. Configure `argocd-image-updater.argoproj.io/git-branch` and (for tag-based strategies) `argocd-image-updater.argoproj.io/tag-base` so the write target is unambiguous.

### Step 5 — Constrain allowed tags and rate-limit

14. Set `argocd-image-updater.argoproj.io/allow-tags` to a semver range (for example `regexp:^v[0-9]+\.[0-9]+\.[0-9]+$`) or a glob (for example `regexp:^main-[0-9a-f]{7,40}$`).
15. Set `argocd-image-updater.argoproj.io/update-strategy: latest` (or `semver`, `digest`, `newer`) and cap with `argocd-image-updater.argoproj.io/force-update: "false"` where you want manual approval.
16. Add per-Application `argocd-image-updater.argoproj.io/pull-policy: Always` only for digest-pinned images, and rate-limit each Application by staggering the global `--interval`.

### Step 6 — Configure notifications on skipped updates

17. Define an Argo CD Notifications service and trigger for `image-updater.skipped` and `image-updater.update-failed` so skipped tags surface to the same channel as sync failures.
18. Subscribe the owning team to both triggers and include the Application name, alias, and skipped reason in the message template.
19. Run a synthetic update by pushing a tag that fails the `allow-tags` filter and confirm the skip notification fires before promoting to production.

## Rollback

- Disable Image Updater in the Helm release (`helm upgrade ... --set server.enabled=false` or scale the deployment to zero) and re-pin the working tag in the Application via a normal PR.
- If a runaway update shipped an exploitable image, freeze tag pushes in the registry (or revoke the tag digest) and use Image Updater's `--git-branch` override to revert to the last known-good manifest.
- If write-back commits are mis-targeted, force the controller to stop with `kubectl scale deploy/argocd-image-updater --replicas=0` and revert the offending branch manually before re-enabling.

## References

- `docs/knowledge/reference/ARGOCD_IMAGE_UPDATER_VERSION_GOVERNANCE.md`
- `docs/knowledge/reference/ARGO_VERSION_GOVERNANCE.md`
- Argo CD Image Updater docs: `https://argocd-image-updater.readthedocs.io/en/stable/`
- Argo CD Notifications docs: `https://argo-cd.readthedocs.io/en/stable/operator-manual/notifications/`
