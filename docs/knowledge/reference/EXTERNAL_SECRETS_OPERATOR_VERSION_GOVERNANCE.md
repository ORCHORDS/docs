---
title: External Secrets Operator Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: External Secrets Operator project (external-secrets/external-secrets); CNCF sandbox; documentation at external-secrets.github.io
---

# External Secrets Operator Version Governance

## Overview

This card governs how `orchords-docs` evaluates External Secrets Operator (ESO) across versions, controller architecture, custom resources, and provider authentication. It is the canonical reference for any KB card that cites Kubernetes-to-external-vault secret synchronization, rotation, or cluster-wide secret fan-out.

ESO is a CNCF sandbox project. It synchronizes secrets from external secret managers (AWS Secrets Manager, HashiCorp Vault, Azure Key Vault, GCP Secret Manager, IBM Cloud Secrets Manager, 1Password, GitHub, etc.) into native Kubernetes `Secret` objects. This card treats ESO as a controlled dependency: CRD version, provider plugin set, and refresh interval policy are decided centrally and inherited by all dependent cards.

## Controller architecture

ESO runs as a single deployment with multiple controllers co-located:

- `externalsecrets` controller: reconciles `ExternalSecret` resources and materializes Kubernetes `Secret` objects.
- `secretstores` controller: validates `SecretStore` and `ClusterSecretStore` reachability and credentials.
- `clusterexternalsecrets` controller (legacy): reconciled by the same binary; scheduled for deprecation in favor of namespaced `ExternalSecret`.
- `pushsecrets` controller: writes secrets back to external providers.
- Webhook server: validates CR schema and enforces immutability flags.
- Pin all sub-resources to a single Helm chart or OCI bundle release; do not mix versions across sub-controllers.

## SecretStore / ClusterSecretStore / ExternalSecret model

The ESO data model separates provider connection from workload binding:

- `SecretStore` (namespaced): provider connection scoped to a single namespace.
- `ClusterSecretStore` (cluster-scoped): provider connection shared across all namespaces.
- `ExternalSecret` (namespaced): declares a target Kubernetes `Secret`, a source key/reference from a store, refresh policy, and transformation rules.
- API group: `external-secrets.io/v1` (current) and `external-secrets.io/v1beta1` (legacy, removed in current release line).
- Pin to `v1`; the operator performs automatic CRD conversion but new fields only exist in `v1`.

References: `https://external-secrets.github.io/external-secrets/`, `https://github.com/external-secrets/external-secrets`.

## PushSecret and rotation

PushSecret (`external-secrets.io/v1alpha1` `PushSecret`) enables writing Kubernetes secrets back to a provider:

- Supported backends include AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault KV v2, and 1Password.
- Rotation strategies: `OnChange` (refresh the external secret when the Kubernetes source changes) and periodic schedules via `rotationInterval`.
- Use `deletionPolicy: Delete` only when the external secret is fully owned by ESO; otherwise use `Retain` to avoid deleting shared credentials.
- Honor provider rate limits: configure `refreshInterval` no faster than the provider's documented quota allows.

## ClusterSecretStore vs SecretStore scope

- Use `SecretStore` by default; it limits blast radius and aligns with namespace tenancy.
- Use `ClusterSecretStore` only for genuinely shared secrets (e.g., platform-wide database credentials) or when onboarding simplicity outweighs namespace isolation.
- Apply RBAC: only platform operators should hold create/update rights on `ClusterSecretStore`; namespace owners get read-only on the binding object.
- Validate that cluster-scoped stores do not embed namespace-specific IAM policies; one store per provider/region/role is the standard pattern.

## Secret refresh / sync interval

- Default `refreshInterval` is 1 hour; tighten to 5–15 minutes only for secrets with explicit RPO requirements.
- Set `refreshInterval: 0` only when an upstream webhook or PushSecret `OnChange` is the authoritative trigger; polling at zero wastes provider quota.
- Honor the controller's `--max-concurrency` setting when fanning out to many stores; tune for provider-side rate limits.
- Record `refreshTime` in the `ExternalSecret` status and alert when refresh falls behind `refreshInterval + jitter`.

## Provider authentication patterns

- AWS: IRSA (IAM Roles for Service Accounts) is the standard; `jwtAuth` style. Avoid long-lived `accessKeyID/secretAccessKey` blocks.
- Vault: Kubernetes auth with `role` and bound `serviceAccount`; rotate the bound token on a defined cadence.
- Azure: Workload Identity for AKS, Managed Identity for AKS Classic; MSI via `pod.identity` is deprecated upstream.
- GCP: Workload Identity Federation with `serviceAccountRef`; `gcpServiceAccountKey` is reserved for legacy bootstrap.
- GitHub: fine-scoped PATs in a separate `Secret`, not inline.
- Always source provider credentials from a bootstrap `Secret` mounted into ESO; never inline them in the `SecretStore` spec.

## ESO roadmap highlights

Current roadmap themes from the project tracker:

- Stabilization of `PushSecret` to `v1beta1` with broader provider support.
- Expanded Vault plugin to cover database and PKI engines.
- Multi-tenancy improvements to `ClusterSecretStore` namespace mapping.
- Refresh-on-annotation support to bypass interval polling without disabling it.
- References: `https://github.com/external-secrets/external-secrets/blob/main/CHANGELOG.md`, `https://external-secrets.github.io/external-secrets/`.

## Upgrading and CRD migrations

1. Read the release notes; identify any `v1beta1` to `v1` field moves and provider-specific removals.
2. Run the operator's built-in CRD conversion before upgrading CRs to `v1`.
3. Upgrade the Helm chart or OCI bundle one minor at a time.
4. Validate that all `SecretStore` and `ClusterSecretStore` objects report `Ready=True` after upgrade; check provider-specific condition reasons.
5. Re-verify a sampled set of `ExternalSecret` objects: confirm Kubernetes `Secret` materialization, ownership reference, and refresh time.
6. Roll back by reinstalling the prior chart version; CRDs are forward-compatible within `v1`.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07. The Knowledge Engineering owner re-validates the CRD API surface, provider matrix, and rotation policy on each cycle and on every ESO minor release.

## References

- ESO docs: `https://external-secrets.github.io/external-secrets/`
- ESO repo: `https://github.com/external-secrets/external-secrets`
- Releases: `https://github.com/external-secrets/external-secrets/releases`
- CRD reference: `https://external-secrets.github.io/external-secrets/api/`
- CNCF ESO: `https://www.cncf.io/projects/external-secrets-operator/`
