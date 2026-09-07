# ApplicationSet Multi-Tenant Rollout Playbook

## Purpose

Adopt Argo CD ApplicationSet for a population of tenants, so that adding a new tenant is a one-line change in a generator list and every tenant automatically gets the right set of `Application` resources across the right set of clusters.

## Audience

Platform engineers, application owners, security engineers reviewing tenant isolation.

## Pre-conditions

- Argo CD ≥ 2.11 with ApplicationSet ≥ 0.5 deployed.
- A baseline `ApplicationSet` template committed in `gitops/appsets/`.
- Per-tenant namespace created in the management cluster.
- RBAC: tenant team limited to their namespace via the platform RBAC bundles.

## Procedure

1. **Author the template**: produce an `ApplicationSet` with a `list` generator (or `cluster` generator) and a templated `Application` for each tenant workload. Set `template.metadata.namespace` to the tenant's namespace.
2. **Codify generator data**: keep the generator list in `gitops/appsets/tenants.yaml`; PR review is mandatory because adding a tenant triggers controller creation.
3. **Sync policy**: set `automated.prune=true` and `automated.selfHeal=true`. Pair with `syncPolicy.syncOptions=[ApplyOutOfSyncOnly=true]`.
4. **Notify**: install Argo CD Notifications with a webhook per tenant to a Slack channel.
5. **Rollout pilot**: enable the template for one tenant in `cluster:` prod-1 only; observe `applicationset_reconciler_duration_seconds{result="success"}` for at least 24 hours.
6. **Promote**: enable for all clusters (`cluster: "*"` or omitted) and the rest of the tenants.
7. **Audit**: enforce Argo CD Server settings `users.policy.csv` and `policies.csv` so that tenants cannot edit others' `Application`s.

## Rollback

- Revert the `ApplicationSet` resource to its previous version; the controller removes Applications based on the deleted entries.
- For a per-tenant emergency stop, set `template.metadata.labels[orchords.com/disabled] = "true"` and patch the ApplicationSet with a label selector that excludes it.

## References

- ApplicationSet documentation — https://argoproj.github.io/argo-cd/applicationset/
- Generator matrix — https://argoproj.github.io/argo-cd/applicationset/Generators/Matrix/
- Internal: Batch 101 reference card `ARGOCD_APPLICATIONSET_GOVERNANCE.md`.
