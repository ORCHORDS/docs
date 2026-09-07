---
title: Kustomize Declarative Configuration Transformation Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Kustomize (kubernetes-sigs/kustomize); SIG-CLI; documentation at kubectl.docs.kubernetes.io/references/kustomize/
---

# Kustomize Declarative Configuration Transformation Version Governance

## Overview

This card governs how `orchords-docs` evaluates Kustomize across built-in (Go library), CLI (`kustomize`), and Kubernetes-native (`kubectl --kustomize`) flavors, the patch format landscape, and the legacy generator directives. It is the reference input for any KB card that cites patch-merge patterns, base/overlay hierarchies, or generator/transformer behavior in a GitOps pipeline.

## Kustomization hierarchy

A Kustomization is a directory tree rooted at a `kustomization.yaml`:

- **Base**: a complete set of manifests that is independently valid; usually vendored from upstream and never edited in place.
- **Overlay**: a directory that pulls one or more bases via `resources:` and adds patches, name prefixes/suffixes, labels, and annotations.
- **Component**: a reusable fragment included from an overlay via `components:` (Kustomize 4.5+); components apply patches and labels but do not stand alone.

Build order is bottom-up: components → bases → overlay. Pin the Kustomization directory layout under change control; the file `kustomization.yaml` is the only authoritative descriptor of the tree.

References: `https://kubectl.docs.kubernetes.io/references/kustomize/builtins/`.

## Built-in vs CLI vs Kubernetes-native

Three different Kustomize engines exist in the wild and they do not all support the same directives:

- **Built-in (Go library)**: vendored by Argo CD, Flux, and many controllers; the version is tied to the consuming binary. Directives supported lag the CLI by one minor.
- **CLI (`kustomize build`)**: standalone binary; ships ahead of the Go library and exposes `kustomize edit set/fix` workflows. Pin by minor and verify against the consumer.
- **Kubernetes-native (`kubectl apply -k`)**: the kube-apiserver bundles a Kustomize build via `kubectl`; the version is whatever the kube release ships. Use for CI parity with `kubectl`; do not expect the same feature set as the CLI.

Always pin the consumer (Argo CD, Flux) to a version that documents which Kustomize Go library version is bundled; otherwise overlays that use newer directives fail at build time.

References: `https://kubectl.docs.kubernetes.io/references/kustomize/cli/`.

## Patch formats

Three patch formats coexist and each has different semantics:

- **Strategic merge patch**: the default for built-in patch directives; uses merge keys (`$patchMergeKey`, `$patchStrategy`) on lists. Behavior is determined by the target resource's openapi schema; CRDs without openapi are not strategic-merge-aware.
- **JSON 6902 patch**: explicit operation list (add/replace/remove); the only format guaranteed to work on CRDs without openapi schemas. Use for CRDs whose strategic-merge behavior is undocumented.
- **Image patch transformer**: a Kustomize-specific transformer (`images:` block) that rewrites container image fields; does not generalize to other fields and is not a JSON 6902 replacement.

Always prefer JSON 6902 for CRDs and strategic merge for core resources with stable schemas.

## vars / replicas / generators (legacy)

These directives were deprecated and then removed across recent Kustomize minors:

- `vars:` — replaced by `replacements:` (Kustomize 4.1+). `replacements:` is positional and does not require a `var:` reference; the new directive must be used for new overlays.
- `replicas:` (legacy `name`/`count` map) — replaced by the modern `replicas:` (list of `{name, count}` objects) and ultimately by the field-aware transformer `scale:`.
- `generators:` (ConfigMap, Secret) — replaced by the dedicated `configMapGenerator:` and `secretGenerator:` directives; the legacy umbrella form was removed.

If a kustomization still uses any of the legacy forms, plan a migration ticket before the next minor bump.

References: `https://kubectl.docs.kubernetes.io/references/kustomize/builtins/#_kustomize_replacements_`.

## Resource reference

Cross-resource references rely on stable names and namespaced scoping:

- Use the resource `id` (`<group>_<version>_<kind>_<namespace>_<name>`) to disambiguate when multiple resources share a name across bases.
- Cross-namespace references are not supported by `replacements:`; the directive operates within the kustomization's output namespace.
- Patch references (e.g., `$patch: subject`) must use the post-transform `name:` to survive namePrefix transforms; pre-transform names break the patch.

## Common base inheritance pitfalls

- Bases that ship their own `namespace:` directive override the overlay's namespace; remove `namespace:` from bases or override it explicitly in the overlay.
- `commonLabels:` apply to selectors; adding or changing labels in an overlay mutates the selector and creates an immutable-field error on existing Deployments.
- `namePrefix:` collides with admission controllers that expect fixed names (e.g., leader-election leases); pin names explicitly or use `nameSuffix:` only when safe.
- Components apply labels to all resources including those brought in by the base; an overlay that adds a label after a component will not see the component's label in selectors.

## Upgrade paths

- Patch bumps (e.g. 5.4.1 → 5.4.2) are drop-in; no manifest changes required.
- Minor bumps (e.g. 5.3 → 5.4) may introduce new defaults (e.g., `LoadBalancerClass` filtering); always run `kustomize build` and diff the output against the prior baseline before merging.
- Major bumps (4.x → 5.x) require migration of `vars:`, `generators:`, and the legacy `replicas:` shape; treat as a separate change ticket.
- Pin the CLI used in CI to a digest; do not rely on `latest`.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07.
