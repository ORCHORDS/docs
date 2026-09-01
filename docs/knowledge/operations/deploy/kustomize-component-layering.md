# Kustomize Component Layering

**Issue:** Kustomize bases and overlays solve the common case of environment-specific configuration, but multi-tenant platforms with shared platform resources and tenant-specific overlays require a composition model that bases cannot express. Kustomize components fill that gap by introducing a third level that can be applied across multiple bases, and operators who skip the component model end up with deeply nested overlays that no one can refactor. Component layering is the discipline that keeps the composition graph navigable as the platform grows.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Components Versus Bases And Overlays

A base is a directory of manifests that an overlay applies patches to. Bases are environment-agnostic; overlays are environment-specific. A component is a slice of configuration that can be added to any base or overlay, regardless of which directory the base lives in. Components are applied through the `components:` field in a kustomization.yaml; they accept their own patches and may include their own generators. This makes them ideal for cross-cutting concerns that should appear in many bases without being duplicated.

Examples of cross-cutting concerns that map cleanly to components: monitoring sidecars injected into every workload, ingress defaults applied to every Service, namespace policies that should attach to every workload in a tenant namespace, default network policies that should be present everywhere. Each is a logical feature whose presence is independent of the workload's specific base, and each is easier to maintain as a component than as a per-base patch.

## Composition Order

The order in which Kustomize applies bases, components, and overlays is significant. Bases apply first, then components, then the top-level overlays. Within each phase, the order of resources is the order they appear in the kustomization.yaml. The output of one phase is the input to the next; components see the output of the base and apply their own patches on top. Overlays see the output of all the components and apply their patches last.

This ordering matters because a component that adds a label will be visible to an overlay that selects on that label. Conversely, an overlay that adds a label will not retroactively affect a component that ran in an earlier phase. Design components assuming they will run after the base and before the overlay, and write overlays assuming components have already finished. The composition order is the operational contract that makes layering predictable.

## Generators In Components

Generators (configMapGenerator, secretGenerator, generator options) work in components with the same semantics as in bases, but the components can be used in multiple places. A component that generates a ConfigMap and patches it into a Deployment will produce a different ConfigMap hash for each application of the component, which means two tenants using the same component will see different ConfigMap names in their namespaces. This is desirable: hash suffixes ensure updates to the component propagate as a new resource, triggering a rolling update.

Hash suffixes can confuse operators who expect the ConfigMap to keep the same name across tenants. The alternative is a generator option that disables the hash, but that option introduces a different operational risk: ConfigMap updates do not trigger Deployment rollouts, and tenants can be running with stale ConfigMaps. The hash suffix is the safer default; train operators to recognize the generated name format.

## Component Versioning And Sharing

Components shared across many tenants should be versioned. The simplest versioning scheme is to put each version in a directory (`components/monitoring/v1`, `components/monitoring/v2`) and update the `components:` reference in each tenant's kustomization to point at the version they want. This is not as ergonomic as semver; the kustomization.yaml does not have a version field for components. But the directory-based approach is auditable: a reviewer can see at a glance which version of which component each tenant uses.

When upgrading a component, expect to migrate multiple tenants. The migration is a per-tenant PR that updates the component reference and any patches that depend on the component's specifics. A breaking change in the component requires a coordinated migration; a non-breaking change can be rolled out per tenant at each tenant's cadence. Document the migration window per component in the platform's release notes.

## Failure Modes

The most common failure is treating components as a substitute for overlays. Components and overlays solve different problems: components add cross-cutting features, overlays express environment-specific differences. Operators who put environment-specific configuration into a component reintroduce the problem components were meant to solve: the component now differs between tenants, and shared upgrades become impossible. Reserve components for genuinely cross-cutting concerns.

A second failure is a component that generates resources but does not declare its dependencies. Kustomize does not enforce ordering between components; if Component A generates a ConfigMap that Component B patches, the result depends on the order in which they are listed. Document the order in the component's README and lint the kustomization to assert the order, or use generators whose hashes are deterministic regardless of order.

A third failure is a component that overlaps with a base's existing resource. Kustomize will refuse to apply a component that adds a resource with the same GroupVersionKind and namespace and name as one already in the base. The failure is loud at apply time but silent in code review. Lint the kustomization locally with `kustomize build` before merging; if the build fails with a duplicate-resource error, the component is incompatible with the base and must be redesigned.

## Canonical sources

1. https://kubectl.docs.kubernetes.io/references/kustomize/components/
2. https://github.com/kubernetes-sigs/kustomize/blob/master/examples/components.md