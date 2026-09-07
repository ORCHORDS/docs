# External Secrets Operator Rollout Playbook

## Purpose

Adopt External Secrets Operator (ESO) to sync secrets from a cloud KMS, Vault, or another external store into Kubernetes Secrets so plaintext credentials never enter Git. The procedure covers provider enablement, secret-store registration, refresh cadence, and rotation handoff to downstream consumers.

## Audience

Platform engineers, security engineers, and application owners who currently embed secrets in Git, Helm values, or CI variables.

## Pre-conditions

- ESO version pinned per `docs/knowledge/reference/EXTERNAL_SECRETS_OPERATOR_VERSION_GOVERNANCE.md`.
- A bootstrap credential in the provider backend has been created (AWS Secrets Manager / GCP Secret Manager / Azure Key Vault / Vault Kubernetes-auth role) and is reachable from the cluster.
- The target `RefreshInterval` is set per the compliance tier of the consumer (for example, 1h for production, 24h for staging).
- RBAC for `SecretStore` and `ExternalSecret` resources is scoped per namespace; cluster-scoped resources require the platform-engineer ClusterRole.
- SOPS is explicitly NOT used for this flow; the cluster has been confirmed SOPS-free for new secret paths.

## Procedure

### Step 1 — Install ESO via Helm

1. Add the ESO Helm repository and pin the chart version from the version-governance reference.
2. Render values: enable the `webhook`, `cert-controller`, and metrics endpoints; set `installCRDs=true`.
3. Install with `helm install external-secrets external-secrets/external-secrets -n external-secrets -f values.yaml`.
4. Confirm the controller, webhook, and cert-controller pods are Ready; confirm the admission webhook is reachable.

### Step 2 — Register a ClusterSecretStore

5. Author a `ClusterSecretStore` (or namespace-scoped `SecretStore`) manifest that points at the chosen provider backend.
6. Reference the provider credential via a Kubernetes Secret that is itself populated by a workload-identity binding (IRSA, Workload Identity, pod identity).
7. Annotate the resource with `refreshInterval` matching the compliance tier.
8. Validate with `kubectl get clustersecretstore <name> -o yaml` and confirm `status.conditions[Ready]=True`.

### Step 3 — Enable the provider plugin

9. Install the matching provider bundle (for example, AWS, GCP, Azure, Vault) as a Helm sub-chart or sidecar.
10. Confirm provider credentials can be listed: `kubectl get secretstore <name>` (or cluster-scoped equivalent) and inspect `status`.
11. Run a smoke test that fetches one non-sensitive metadata field from the provider; this proves the chain without exposing a real secret.

### Step 4 — Deploy the first ExternalSecret

12. Author an `ExternalSecret` manifest that maps provider keys to Kubernetes Secret keys; set `metadata.labels` to match consumer selectors.
13. Apply the manifest; confirm a corresponding Kubernetes Secret is created and that the data matches the source via a hash diff.
14. Rotate the value in the provider backend and confirm the Kubernetes Secret updates within `refreshInterval`.

### Step 5 — Set RefreshInterval and rotation cadence

15. Update `spec.refreshInterval` on each `ExternalSecret` so it matches the consumer's rotation SLA.
16. Configure `spec.dataRemoteRef.refreshInterval` only when a single key needs a tighter cadence than the parent store.
17. Document the cadence in the runbook so application owners can audit how often secrets rotate.

### Step 6 — Prepare PushSecret for rotation handoff

18. Enable `PushSecret` so that rotated values can be pushed back to the provider (Vault dynamic credentials, AWS managed rotation).
19. Author a `PushSecret` manifest with `metadata.name` aligned to the originating `ExternalSecret`.
20. Validate the round-trip: rotate in the provider, confirm the Kubernetes Secret updates, and confirm the reverse PushSecret re-writes the new value back to the provider.

## Rollback

- Uninstall the Helm release and the provider CRDs: `helm uninstall external-secrets -n external-secrets` followed by `kubectl delete crd clustersecretstores.external-secrets.io secretstores.external-secrets.io externalsecrets.external-secrets.io pushsecrets.external-secrets.io`.
- List orphan Secrets with `kubectl get secrets -A -l external-secrets.io/store=<store>` and confirm which must be removed manually versus which will be garbage collected by the namespace.
- During a security incident, audit who can read Secrets: `kubectl auth can-i get secrets --as=system:serviceaccount:<ns>:<sa> -n <ns>`.
- Secret deletion is handled by Kubernetes garbage collection: deleting the owning `ExternalSecret` does not delete the resulting Secret by default, so include `data` cleanup or use a `DeletionPolicy` of `Delete` to opt in.

## References

- `docs/knowledge/reference/EXTERNAL_SECRETS_OPERATOR_VERSION_GOVERNANCE.md`
- External Secrets Operator docs: `https://external-secrets.io/latest/`
- ClusterSecretStore reference: `https://external-secrets.io/latest/api/clustersecretstore/`
- PushSecret reference: `https://external-secrets.io/latest/api/pushsecret/`
