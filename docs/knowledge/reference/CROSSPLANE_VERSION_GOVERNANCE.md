---
title: Crossplane Cloud Control Plane Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Crossplane project (crossplane/crossplane); CNCF incubating; documentation at docs.crossplane.io
---

# Crossplane Cloud Control Plane Version Governance

## Overview

This card governs how `orchords-docs` evaluates Crossplane across versions, the provider/configuration/composition/claim model, composition function runtimes, and CRD upgrade paths. It is the reference input for any KB card that cites external resource orchestration, claim-driven APIs, or composition revision rollback in a Kubernetes-native control plane.

## Control plane architecture

The Crossplane control plane is a Kubernetes cluster (often the same cluster that runs workloads, but frequently a dedicated cluster) that hosts a stack of CRDs and controllers:

- **Providers**: in-cluster controllers that translate Crossplane Managed Resources (MRs) into calls to an external API (AWS, GCP, Azure, Kubernetes, Helm, SQL, etc.). Each provider ships its own CRD family.
- **Configurations**: versioned, installable bundles of XRDs, Compositions, and provider dependencies; distributed as OCI artifacts and pinned by tag/digest.
- **Composite Resource Definitions (XRDs)**: cluster-scoped (`apiextensions.crossplane.io/v1`) schemas that declare the developer-facing API; an XRD has one or more Compositions bound to it.
- **Compositions**: cluster-scoped templates that translate a Composite Resource (XR) into a graph of Managed Resources (MRs).
- **Claims**: namespaced (`apiextensions.crossplane.io/v1beta1`) references that bind a developer to an XR; the claim is the only API most consumers should touch.

The control plane cluster is independent from the workload cluster; cross-plane network reachability and provider credentials are deployment-time concerns.

References: `https://docs.crossplane.io/latest/concepts/`.

## Provider families

Providers fall into three families with materially different lifecycles:

- **UpCloud/AWS/GCP/Azure family** (community + vendor): the canonical Provider family, versioned per cloud; pinned per `Provider` resource and updated by changing `spec.package` to a new image and digest.
- **provider-kubernetes** and **provider-helm**: bring Kubernetes-style manifests and Helm charts under Crossplane; both rely on an in-cluster runner and require explicit credential wiring.
- **provider-sql** and **provider-nomad**: legacy families; SQL is the only one of these that is still actively maintained and ships a composition-function bridge.

Pin each provider to a digest that matches the running Crossplane minor; provider CRDs and Crossplane CRDs are not independently versioned.

References: `https://marketplace.upbound.io/providers`.

## Managed resource lifecycle

Each Managed Resource is a Kubernetes object whose controller reconciles against the external system:

- `spec.forProvider` carries the desired external state; `status.atProvider` carries the observed external state.
- The reconciler honors `spec.managementPolicies` (`FullControl`, `ObserveOnly`, `OrphanOnDelete`); default is `FullControl`. Switching from `ObserveOnly` to `FullControl` after a delete is a destructive operation.
- `spec.deletionPolicy` (`Delete`, `Retain`) governs behavior when the MR is removed; default `Delete` is rarely safe for production databases or persistent storage.
- Health is exposed via `status.conditions[type=Ready]`; `Synced=False` indicates the provider failed to push the desired state.
- Connection secrets are written by providers to a `Secret` named in `spec.writeConnectionSecretToRef`; treat the secret as sensitive and gate it with RBAC.

## Composition functions (Go/Python/Environment)

The classic Composition (`spec.resources` array) has been superseded by the Composition Functions pipeline:

- **Environment (Go templates)**: the default; uses `gotemplate` to render resource bodies, supports `to:` conversion hooks and observability via `status.conditions`.
- **Containerized functions (Go/Python)**: arbitrary container images invoked with the desired XR and observed MRs; the function returns a list of desired resources. Functions are versioned and pinned per Composition.
- **Status functions**: container functions that update the XR's `status` only, without affecting `spec.resources`.

Each function call is bounded by a timeout; long-running functions must implement checkpointing or be split. Pin function images by digest; tag-only references are not acceptable.

References: `https://docs.crossplane.io/latest/concepts/composition-functions/`.

## Composition revisions and rollback

Compositions are immutable in production; changes are made by introducing a new Composition with the same name but a new revision:

- Each XR pins to a Composition by name and `revision`; older revisions remain available until they are removed from the cluster.
- To roll back, change `spec.compositionRef.revision` on the affected XRs (or use a Composition update policy that auto-bumps).
- The `CompositionUpdatePolicy` (`Automatic` or `Manual`) on the XRD governs whether existing XRs follow the latest Composition automatically.
- Never edit a live Composition in place; the controller will reject the change and the resulting state is undefined.

## RBAC at the control plane boundary

The cluster boundary between the control plane and developer/consumer clusters is enforced by Kubernetes RBAC:

- Developers consume Claims (`XClaim`) in their namespaces; they do not need access to MRs or Compositions.
- Platform engineers have access to XRDs and Compositions; read-only access is sufficient to publish a new Configuration.
- Provider credentials are bound to the provider's ServiceAccount via `ProviderConfig`; rotate by issuing a new `ProviderConfig` and switching `spec.providerConfigRef`.
- External Secrets / SOPS are not built in; credentials land as Kubernetes Secrets and must be encrypted at rest with a KMS provider.

## Upgrade and CRD migration

Crossplane is installed as a Helm chart (`crossplane`); the chart version is the source of truth for the controller and CRD versions.

- Pin the chart to a minor and verify the controller image digest matches the published SLSA provenance.
- CRD upgrades are part of the chart upgrade; never install a controller image ahead of its CRDs.
- Provider CRDs upgrade with the Provider package; older MRs with deprecated fields must be migrated before the provider minor bump that removes the field.
- Upgrade order: providers first (so MRs can be reconciled against the new schemas), then Crossplane core, then XRD revisions (so Claims pick up the new shape).

References: `https://docs.crossplane.io/latest/getting-started/install/`.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07.
