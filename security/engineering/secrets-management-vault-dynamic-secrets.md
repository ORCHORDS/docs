# Secrets Management — HashiCorp Vault Dynamic Secrets, Rotation, and Kubernetes Integration

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application stores database credentials in environment variables
that were provisioned six months ago. The same password is shared
across staging and production. A developer leaves the company and
you realize the credentials cannot be rotated without redeploying
12 services simultaneously. Meanwhile, your CI/CD pipeline uses a
long-lived Vault root token stored in a GitHub secret, and your
security audit flags that no secret has been rotated in the past
year.

## Context

HashiCorp Vault centralizes secrets management with dynamic secrets,
automatic rotation, and identity-based access. Dynamic secrets are
generated on demand with short TTLs (typically 1 hour) and
automatically revoked when the lease expires — no human or cron job
required. Vault's Kubernetes auth method lets pods authenticate
using their service account JWT, eliminating the "secret zero"
bootstrap problem. Three integration patterns exist for Kubernetes:
Agent Sidecar Injector, CSI Provider, and Vault Secrets Operator
(VSO). The transit secrets engine provides encryption as a service
without exposing keys to applications.

## Dynamic secrets

```bash
# Enable database secrets engine
vault secrets enable database

# Configure PostgreSQL connection
vault write database/config/my-postgres \
  plugin_name=postgresql-database-plugin \
  connection_url="postgresql://{{username}}:{{password}}@db:5432/app" \
  allowed_roles="readonly" \
  username="vaultadmin" password="..."

# Create a role with short-lived credentials
vault write database/roles/readonly \
  db_name=my-postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN \
    PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; \
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl="1h" max_ttl="24h"

# Application requests credentials — unique per request
vault read database/creds/readonly
# Returns: username=v-token-readonly-abc123, password=..., lease_id=...
```

```
Dynamic secrets lifecycle:

  App requests creds → Vault generates unique user/pass
  → Lease starts (default 1h) → App uses creds
  → Lease expires → Vault revokes creds automatically

  No shared passwords. No manual rotation.
  Each service instance gets its own credential set.
```

## Static role rotation

```bash
# For systems where dynamic per-request creds aren't practical
vault write database/static-roles/app-user \
  db_name=my-postgres \
  username="app_user" \
  rotation_period="24h"

# Vault owns the password and rotates it on schedule
# Application reads the current password from Vault
vault read database/static-creds/app-user
```

## Transit secrets engine (encryption as a service)

```bash
# Enable transit engine
vault secrets enable transit

# Create an encryption key
vault write -f transit/keys/orders-key

# Encrypt — app never sees the raw key
vault write transit/encrypt/orders-key \
  plaintext=$(base64 <<< "sensitive data")
# Returns: ciphertext: vault:v1:abc123...

# Decrypt
vault write transit/decrypt/orders-key \
  ciphertext="vault:v1:abc123..."

# Rotate key — new encryptions use v2, old ciphertext still decryptable
vault write -f transit/keys/orders-key/rotate

# Force minimum decryption version (invalidates old ciphertext)
vault write transit/keys/orders-key/config min_decryption_version=2
```

## PKI secrets engine

```bash
# Issue short-lived X.509 certificates dynamically
vault secrets enable pki
vault secrets tune -max-lease-ttl=87600h pki

# Configure root CA
vault write pki/root/generate/internal \
  common_name="example.com" ttl=87600h

# Create a role for issuing certs
vault write pki/roles/web-server \
  allowed_domains="example.com" \
  allow_subdomains=true \
  max_ttl="24h"

# Issue a certificate (24h TTL — no CRL/OCSP needed)
vault write pki/issue/web-server \
  common_name="api.example.com" ttl="24h"
```

## Kubernetes authentication

```bash
# Enable Kubernetes auth method
vault auth enable kubernetes

# Configure — Vault validates pod JWTs against K8s TokenReview API
vault write auth/kubernetes/config \
  kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443"

# Bind a role to a specific service account
vault write auth/kubernetes/role/myapp \
  bound_service_account_names=myapp-sa \
  bound_service_account_namespaces=default \
  policies=myapp-policy \
  ttl=1h
```

```
Kubernetes integration patterns:

  Pattern                  How it works                    App changes
  ─────────────────────────────────────────────────────────────────────
  Agent Sidecar Injector   Mutating webhook injects        Zero (reads
                           init + sidecar containers,      from shared
                           renders secrets to volume        volume)

  CSI Provider             Mounts secrets via Secrets      Zero (reads
                           Store CSI driver as volume       from volume)

  Vault Secrets Operator   K8s operator syncs Vault        Zero (reads
  (VSO)                    secrets into K8s Secret          K8s Secret)
                           objects
```

```yaml
# Agent Sidecar Injector — pod annotations
metadata:
  annotations:
    vault.hashicorp.com/agent-inject: "true"
    vault.hashicorp.com/role: "myapp"
    vault.hashicorp.com/agent-inject-secret-db-creds: "database/creds/readonly"
    vault.hashicorp.com/agent-inject-template-db-creds: |
      {{- with secret "database/creds/readonly" -}}
      postgresql://{{ .Data.username }}:{{ .Data.password }}@db:5432/app
      {{- end }}
```

## Anti-patterns

- **Using the root token in applications** — root tokens never expire
  and cannot be scoped. Revoke after initial setup and use AppRole or
  Kubernetes auth for application access.
- **No lease renewal logic** — most applications get token renewal
  wrong or skip it entirely, causing surprise 403s when leases expire
  mid-request. Implement renewal before 75% of TTL elapses.
- **Long default TTLs causing lease explosions** — leaving default
  TTLs unchanged causes leases to accumulate in memory, degrading
  Vault performance. Set appropriate TTLs per secrets engine.
- **Static shared credentials across services** — defeats the purpose
  of Vault. Use per-service dynamic secrets with unique credentials
  per instance.

## Gotchas

- **TTL changes are not retroactive** — adjusting TTL policy only
  affects leases and tokens issued after the change. Existing leases
  retain their original TTL until they expire or are explicitly
  revoked.
- **Binding roles to the default service account** — always bind to
  a dedicated, least-privilege service account per application, not
  the namespace's default.
- **Long-lived CI/CD tokens** — using static Vault tokens in CI
  pipelines is a core anti-pattern. Use AppRole with short-lived
  tokens or Kubernetes auth from CI runners.
- **Agent sidecar init ordering** — the init container must complete
  before the application container starts. If Vault is unreachable
  during pod startup, the pod hangs indefinitely. Configure
  `vault.hashicorp.com/agent-pre-populate-only` for one-shot mode
  when continuous renewal is not needed.

## Verification

- Dynamic secrets enabled for database access with TTL under 24 hours.
- Root token revoked after initial Vault setup.
- Kubernetes auth method configured with dedicated service accounts.
- Lease renewal logic implemented in application code or via Agent.
- Transit engine used for application-layer encryption.
- Secret rotation period configured and tested.

## Related

- `documentation/categories/security/supply-chain-security-slsa-sigstore.md`
- `documentation/categories/infra/kubernetes-network-policies-service-mesh.md`
- `documentation/categories/github/actions-security-hardening.md`

## Source URLs (verified 2026-08-16)

- HashiCorp Vault Deep Dive: Dynamic Secrets, Kubernetes Auth, PKI — https://pub.towardsai.net/hashicorp-vault-deep-dive-28f2fa00a610
- Kubernetes Vault Integration Patterns — https://www.hashicorp.com/en/blog/kubernetes-vault-integration-via-sidecar-agent-injector-vs-csi-provider
- Vault Anti-Patterns (HashiCorp Well-Architected Framework) — https://developer.hashicorp.com/well-architected-framework/operational-excellence/security-vault-anti-patterns
- Database Secrets Engine Documentation — https://developer.hashicorp.com/vault/docs/secrets/databases
