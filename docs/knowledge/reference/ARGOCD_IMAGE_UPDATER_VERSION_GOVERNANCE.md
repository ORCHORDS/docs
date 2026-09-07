---
title: Argo CD Image Updater Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Argo CD Image Updater project (argoproj-labs/argocd-image-updater); Argo Labs sub-project; documentation at argocd-image-updater.readthedocs.io
---

# Argo CD Image Updater Version Governance

## Overview

This card governs the Argo CD Image Updater, the Argoproj Labs sub-project that watches container registries, finds new tags for images referenced by Argo CD `Application` and `ApplicationSet` resources, and rewrites manifests via Git to keep the cluster in sync. It is the reference for any KB card touching automatic container image promotion, GitOps pull-through, or registry authentication for declarative clusters.

## Image registry authentication patterns

- Authentication is per-registry and is declared in a `argocd-image-updater` `Secret` of type `kubernetes.io/dockerconfigjson` (legacy: `argocd-image-updater/secret`) in the same namespace as the controller, typically `argocd`.
- For Amazon ECR, prefer IAM roles for service accounts (IRSA) with an `ECR:BatchGetImage` / `ECR:GetDownloadUrlForLayer` policy; the controller can also use static credentials via the `Secret` for shared dev environments.
- For Google Artifact Registry / Container Registry, mount a service-account JSON key into the `Secret` and reference it under `creds.existingSecretName` in the registry block of the `ConfigMap`.
- For Azure Container Registry, use the workload-identity-backed federated credential; static `dockerconfigjson` is acceptable only in non-production.
- Multi-registry setups should namespace secrets by registry hostname (`registry-docker-hub`, `registry-ghcr-io`) and pin each secret to a single `application-name` set.
- Pin registry API endpoints; never use `https://index.docker.io/v1/` with a static credential longer than 90 days.

## Commit / Git / Announce strategies

- `commit`: Image Updater commits the rendered manifest back to the source Git repository; this is the default and the only fully declarative mode.
- `git`: similar to `commit`, but lets the operator configure a custom branch prefix and commit author; use this when the GitOps repo enforces a bot identity.
- `announce`: the controller writes the new image tag to the Argo CD `Application`'s `argocd-image-updater/image-list` annotation, leaving the manifest untouched. Pair this with a webhook that triggers an Argo CD `ImageUpdater` controller in dry-run mode for visibility-only workflows.
- For `commit`/`git`, set `git.commit-message` to include the `Application` name and old/new tags so reviewers can audit promotions from the Git log.
- Never enable `write-back-method: argocd` in production; the Argo CD-side write-back writes to the `Application`'s live spec and bypasses Git history.

## Tag filtering with semver and glob

- `semver`: filter tags with strict `major.minor.patch` semantics. Use `matchConstraint: ">=1.0.0 <2.0.0"` to pin a major and accept patch updates.
- `glob`: a simpler `*`-style matcher for repositories that do not publish semver (e.g., date-stamped tags like `2026-09-07-*`); combine with `latestN` or `sortOrder: asc`.
- `latestN`: keep only the top N most recently published tags after constraint evaluation; the default is `1` (a single new tag).
- Pre-release tags (`-rc1`, `-alpha.0`) are skipped unless `allowPreRelease: true` is set; this prevents unreleased code from being auto-promoted.
- Tag mutation strategy (`digest`, `rebase`, `merge`) controls how the image reference is rewritten; default `latest` works for floating-tag promotion, while `digest` is required when content trust is enforced via cosign.

## Update policy and rate-limit

- The global rate limit (`registries.tier` per registry and `policies.update-strategy`) defaults to one update per `Application` per registry poll cycle; tune with `--interval` (minimum 1m).
- The `update-strategy` field supports `newest`, `semver`, and `glob`; choose `semver` for libraries and `newest` for image-only services.
- Always set `--once-at-startup: false` outside of break-glass scenarios, otherwise a controller restart triggers an immediate flood of updates.
- Bound updates with `batch-size` and stagger `--interval` per registry tier to stay below upstream rate limits (e.g., 5 req/s for Docker Hub anonymous).
- Use `applications.apps.codecentric.com/v1alpha1` or built-in labels (`argocd-image-updater.argoproj.io/registries`) to scope polling to specific tenants.

## Multi-cluster registrations and ArgoCD Application match expressions

- Image Updater supports a list of registered Argo CD instances (server addresses) when running in multi-cluster hub mode; each registration uses its own kubeconfig token and Application cache.
- `matchApplicationName` and `matchApplicationLabels` filter which `Application`s are managed by which controller instance; use label selectors (`argocd-image-updater.io/managed-by: cluster-a`) to prevent cross-tenant updates.
- For `ApplicationSet`, declare the `template` generator's image override on the `template.spec.source.kustomize.image` field; Image Updater walks the generated children and rewrites the parent image field, keeping generator metadata intact.
- Avoid mixing `ApplicationSet` and standalone `Application` references for the same image in the same cluster; the controller will treat them as separate units and may double-promote.

## Health assessment of updated workloads

- Image Updater triggers an Argo CD sync after a successful commit; health is the standard Argo CD health (`Healthy`, `Degraded`, `Progressing`, `Missing`, `Suspended`).
- Configure `argocd.argoproj.io/refresh: hard` annotation on the `Application` so post-update rollouts do not get short-circuited.
- Treat `Degraded` post-sync as a failure that requires manual intervention; do not auto-rollback on first failure.
- For canary services, layer Image Updater with Argo Rollouts so a degraded promotion routes traffic back to the previous ReplicaSet.

## Rollback to previous tag

- The controller does not have a native rollback primitive; rollback is performed via Git revert of the most recent image-promotion commit and a subsequent Argo CD refresh.
- Enable `image-list` annotation tracking on every `Application` (default) so the previous tag is visible via `kubectl get application -o jsonpath` for incident response.
- For automated rollback, combine Image Updater with a health-check sidecar that calls `kubectl annotate application <name> argocd-image-updater.argoproj.io/rollback-target=<oldTag>`.
- Always keep the prior `Application`'s `source.helm.values` commit in Git history; do not rewrite history with force-push during a rollback.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07. The card is re-evaluated on each upstream Image Updater minor, on any Argo CD compatibility-window change, and on registry-policy changes (e.g., Docker Hub pull limits, GHCR token TTLs).

## References

- Upstream repository: `https://github.com/argoproj-labs/argocd-image-updater`
- Documentation: `https://argocd-image-updater.readthedocs.io/`
- Releases and changelog: `https://github.com/argoproj-labs/argocd-image-updater/releases`
- Configuration reference: `https://argocd-image-updater.readthedocs.io/en/stable/configuration/`
- Argo CD core project: `https://github.com/argoproj/argo-cd`
- Argo Project site: `https://argoproj.github.io/`
- ApplicationSet integration: `https://github.com/argoproj-labs/applicationset`
