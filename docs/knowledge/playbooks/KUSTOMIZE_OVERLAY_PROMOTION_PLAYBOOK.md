# Kustomize Overlay Promotion Playbook

## Purpose

Promote Kubernetes manifests through dev, stage, and prod using Kustomize overlays with auditable patches, images, and environment variables.

## Audience

Platform engineers, GitOps operators (FluxCD / ArgoCD), application teams shipping per-environment configs.

## Pre-conditions

- `docs/knowledge/reference/KUSTOMIZE_VERSION_GOVERNANCE.md` reviewed and the supported kustomize binary version pinned.
- The `base/` and `overlays/<env>/` directory convention agreed and reflected in the repo layout.
- CI runs `kubectl kustomize <overlay> | kubeconform -strict` as a required check on every PR.
- Kustomize binary pinned in `tools/kustomize/<version>` and verified via `kustomize version`.

## Procedure

### Step 1 — Skeleton the base

1. Create `base/kustomization.yaml` referencing the raw manifests: `resources:`, `commonLabels:`, `namespace:`.
2. Keep `base/` free of environment-specific values; only cross-cutting labels, annotations, and names live here.
3. Validate with `kustomize build base | kubeconform -strict -summary`.

### Step 2 — Add an overlay per environment

1. Create `overlays/dev/`, `overlays/stage/`, `overlays/prod/` with their own `kustomization.yaml`.
2. Use `resources: [../../base]` to compose, then declare per-environment `namespace`, `namePrefix`, and `commonAnnotations`.
3. Keep a one-to-one mapping between overlay directory and target cluster/namespace.

### Step 3 — Apply patches

1. Prefer strategic-merge or JSON 6902 patches via `patches:` or `patchesStrategicMerge:` (legacy); document the rationale.
2. Scope patches to the smallest set of fields needed; avoid wholesale resource replacements that drift from base.
3. Annotate every patch with an inline comment citing the change request or incident it addresses.

### Step 4 — Pin images and env

1. Use the kustomize `images:` field to rewrite tags and digests without editing manifests: `images: [{name: <repo>, newTag: <digest>}]`.
2. Use `configMapGenerator` / `secretGenerator` with `env:` sources for environment variables; never inline raw secrets.
3. Re-render with `kustomize build overlays/prod` and confirm no plaintext secrets remain.

### Step 5 — Validate the diff before promotion

1. `kubectl kustomize overlays/prod > /tmp/rendered.yaml` and run `kubectl diff -f /tmp/rendered.yaml` against the live cluster.
2. CI must run `kustomize build` dry-run with schema validation on every PR touching any overlay.
3. Two reviewers required for any change that touches `overlays/prod/`.

### Step 6 — Gate promotion through PR and GitOps

1. Merge promotion PR; Flux/ArgoCD observes the change and reconciles the cluster.
2. Confirm `kubectl get applications -n argocd` (or `flux get kustomizations`) shows Healthy and Synced.
3. Capture the rendered manifest digest in the release notes for audit traceability.

## Rollback

- Revert the offending PR; Flux/ArgoCD reconciles back to the previous commit automatically.
- Never edit an overlay directly in a running cluster without re-running kustomize; patches must stay in Git.
- Clean up dangling components only on confirmed orphan namespaces via `kustomize build overlays/<env> | kubectl delete -f -` after explicit sign-off.

## References

- `docs/knowledge/reference/KUSTOMIZE_VERSION_GOVERNANCE.md`
- kubectl kustomize: https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/
- Kustomize patches: https://kubectl.docs.kubernetes.io/references/kustomize/patches/
