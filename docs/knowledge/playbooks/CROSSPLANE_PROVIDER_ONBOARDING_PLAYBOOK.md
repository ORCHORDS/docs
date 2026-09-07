# Crossplane Provider Onboarding Playbook

## Purpose

Onboard a Crossplane provider package, define an XRD and Composition, and expose managed resources to application teams via Claims.

## Audience

Platform engineers, cloud governance, application teams consuming Claim-shaped resources.

## Pre-conditions

- `docs/knowledge/reference/CROSSPLANE_VERSION_GOVERNANCE.md` reviewed and the supported Crossplane Helm chart version pinned.
- Crossplane installed via the official Helm chart and `kubectl get pods -n crossplane-system` reports all pods Healthy.
- Provider package pulled from `xpkg.crossplane.io` or `crossplane/pkg` and pinned to a digest.
- Provider credentials bootstrapped via IRSA (EKS), Workload Identity (GKE), or workload identity federation (AKS).

## Procedure

### Step 1 — Install the provider

1. Apply the `Provider` manifest with `spec.package` pinned to a digest, not a mutable tag.
2. Confirm `kubectl get providers` reaches `INSTALLED=True` and `HEALTHY=True` within the reconcile window.
3. Verify provider controller pod is running and watching the right CRDs.

### Step 2 — Install the provider Configuration

1. Apply a `Configuration` resource from a curated package that pre-bundles XRDs and Compositions.
2. Track the upstream `Configuration` revision so upgrades are intentional.
3. Confirm `kubectl get configurations` reports `INSTALLED=True`.

### Step 3 — Author the XRD

1. Define a `CompositeResourceDefinition` with a `claimNames` section naming the Claim CRD application teams will use.
2. Specify the schema in `spec.versions[].schema.openAPIV3Schema`; every field must have a description and constraint.
3. Apply and confirm the Claim CRD is registered: `kubectl get crds | grep <xrd-name>`.

### Step 4 — Write the Composition (functions pipeline)

1. Author a `Composition` referencing the XRD by name; build a `pipeline` of composition functions (e.g., `crossplane.fn`).
2. Map Claim fields to managed resource fields via `function-patch-and-transform` and any cloud-specific function.
3. Validate locally with `crossplane render` against a sample Claim YAML.

### Step 5 — Test with a sandbox Claim

1. Submit a Claim in a sandbox namespace; confirm a `CompositeResource` (XR) is created and reconciled.
2. Confirm every referenced `ManagedResource` reaches `READY=True` and `SYNCED=True`.
3. Tear down the sandbox Claim and verify all managed resources are deleted (no orphans).

### Step 6 — Expose via Claim grant and version

1. Issue a `Claim` namespace grant (namespace-scoped RBAC) so application teams can create Claims only in their namespaces.
2. Tag the `Composition` with `metadata.annotations[crossplane.io/version]` and document it in the changelog.
3. Publish the Claim API contract in the internal developer portal; point app teams to the example Claim YAML.

## Rollback

- Uninstall the provider and Configuration with `kubectl delete provider,configuration -n crossplane-system --all`.
- Resolve dead Claims that point at ghost Managed resources before deletion; use `kubectl describe claim` to find bound MRs.
- Revoke any `claim grant` once the Composition is removed; never delete a provider while Claims still bind through it.

## References

- `docs/knowledge/reference/CROSSPLANE_VERSION_GOVERNANCE.md`
- Crossplane providers: https://docs.crossplane.io/latest/concepts/providers/
- Composition functions: https://docs.crossplane.io/latest/concepts/composition-functions/
