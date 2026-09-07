# cert-manager Adoption Playbook

## Purpose

Adopt cert-manager in a Kubernetes cluster so that all in-cluster certificates are issued, renewed, rotated, and revoked by cert-manager with no manual `openssl` workflows.

## Audience

Platform engineers, security engineers, application teams transitioning from manually managed certs.

## Pre-conditions

- cert-manager >= 1.15 deployed (see Batch 104 reference card `CERT_MANAGER_VERSION_GOVERNANCE.md`).
- An ACME account (Let's Encrypt staging then production) or internal CA configured.
- `kubectl cert-manager` plugin installed.
- Inventory of existing manually-managed certs in the cluster.

## Procedure

1. **Deploy cert-manager**: `kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml` against a staging cluster.
2. **Configure issuers**: create `ClusterIssuer` resources for `letsencrypt-staging` and `letsencrypt-prod` (and `internal-ca` if applicable). Test with a temporary certificate request.
3. **Annotate ingress controllers**: enable the `cert-manager.io/cluster-issuer` annotation on each `Ingress`.
4. **Migrate existing certs**: for every manually-managed secret, create a matching `Certificate` resource that references the same secret. Trigger issuance and verify the secret is renewed by cert-manager.
5. **Set renewal windows**: configure `spec.renewBefore` to `720h` (30 days) for public certs and `168h` (7 days) for internal certs.
6. **Disable legacy workflows**: lock down the legacy `cert-rotation` pipeline so that only cert-manager can renew secrets.
7. **Document**: add a runbook entry to `policies/tls/cert-manager.md`.

## Rollback

- Revert the issuer and ingress controller configuration.
- Manually re-issue any certificates that were migrated, restoring the legacy secret.
- Cert-manager CRDs can be left installed in a paused state until re-adoption.

## References

- cert-manager docs — https://cert-manager.io/docs/
- Internal reference card: `CERT_MANAGER_VERSION_GOVERNANCE.md`.
- ClusterIssuer reference — https://cert-manager.io/docs/reference/api-reference/#clusterissuer
