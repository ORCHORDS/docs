# Vault Dynamic Secrets for Cloudflare Workers

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Long-lived database passwords and Cloudflare API tokens committed
to `.env` files or stored as static Kubernetes secrets accumulate
silently. When a credential leaks, the blast radius spans every
service sharing that credential, and rotation requires coordinated
restarts across multiple environments.

## Context

HashiCorp Vault's secrets engine replaces static credentials with
dynamically generated, short-lived credentials. For PostgreSQL,
Vault creates a unique username/password pair per request with a
configurable TTL. For Cloudflare Workers, static Wrangler secrets
(`wrangler secret put`) remain appropriate for non-rotatable
values; Vault is used for tokens that can be regenerated on a
schedule via the transit engine or a custom secrets plugin.

This entry covers the Vault database secrets engine for PostgreSQL,
Kubernetes auth and the Vault agent sidecar, rotating Cloudflare
API tokens via Vault, comparing Vault vs. Wrangler secrets, and
TTL / lease renewal patterns.

Vault version: 1.17+. Vault Agent: 1.17+.

## 1. Vault Database Secrets Engine: PostgreSQL

Enable the secrets engine and configure the root connection once:

```bash
vault secrets enable database

vault write database/config/example project-pg \
  plugin_name=postgresql-database-plugin \
  allowed_roles="app-role" \
  connection_url="postgresql://{{username}}:{{password}}@pg.internal:5432/example project?sslmode=require" \
  username="vault_root" \
  password="<root-password>" \
  password_authentication="scram-sha-256"
```

Define the role that Workers or services request credentials from:

```bash
vault write database/roles/app-role \
  db_name=example project-pg \
  creation_statements="CREATE ROLE \"{{name}}\" \
    WITH LOGIN PASSWORD '{{password}}' \
    VALID UNTIL '{{expiration}}'; \
    GRANT SELECT, INSERT, UPDATE, DELETE \
    ON ALL TABLES IN SCHEMA public \
    TO \"{{name}}\";" \
  revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"
```

Request a credential at deploy time or from the sidecar:

```bash
vault read database/creds/app-role
# Key       Value
# username  v-token-app-role-AbCdEf...
# password  A1b-2Cd-...
# lease_id  database/creds/app-role/abc123
# lease_duration 1h
```

## 2. Kubernetes Auth and Vault Agent Sidecar

Authenticate pods to Vault using the Kubernetes service-account
token without embedding a Vault token in the deployment manifest:

```bash
vault auth enable kubernetes

vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc" \
  kubernetes_ca_cert=@/run/secrets/kubernetes.io/serviceaccount/ca.crt

vault write auth/kubernetes/role/example project-api \
  bound_service_account_names=example project-api \
  bound_service_account_namespaces=example project \
  policies=example project-policy \
  ttl=1h
```

Vault Agent sidecar annotation snippet (injected by the Vault
Agent Injector mutating webhook):

```yaml
spec:
  serviceAccountName: example project-api
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "example project-api"
        vault.hashicorp.com/agent-inject-secret-db: |
          database/creds/app-role
        vault.hashicorp.com/agent-inject-template-db: |
          {{- with secret "database/creds/app-role" -}}
          DATABASE_URL=postgresql://{{ .Data.username }}:{{ .Data.password }}@pg.internal:5432/example project
          {{- end }}
```

The credential file is written to `/vault/secrets/db` and
sourced by the application at startup. The agent renews the lease
before expiry and rewrites the file; the application must watch
the file or restart on SIGHUP to pick up rotated credentials.

## 3. Rotating Cloudflare API Tokens via Vault

Cloudflare API tokens cannot be retrieved after creation; however,
the token value can be stored as a Vault KV secret and rotated
on a schedule using a Vault policy + external rotation script or
the Vault Cloudflare provider (community):

```bash
# Store the initial token in KV v2
vault kv put secret/cloudflare/api-token \
  value="<CF_API_TOKEN>" \
  created_at="2026-08-17"

# Read in CI or from agent template
vault kv get -field=value secret/cloudflare/api-token
```

Rotation workflow (executed by a periodic Vault token or a cron
job with `vault` CLI access):

```
1. Create a new Cloudflare API token via CF REST API.
2. vault kv put secret/cloudflare/api-token value=<new-token>.
3. Deploy Workers with new token: wrangler deploy.
4. Revoke the old token via CF REST API.
5. Confirm the rotation in Vault audit log.
```

## 4. Vault vs. Wrangler Secrets: Decision Table

```
+-----------------------------+------------------+-------------------+
| Property                    | wrangler secret  | Vault KV / engine |
+-----------------------------+------------------+-------------------+
| Stored in Cloudflare        | Yes              | No                |
| Rotation support            | Manual           | Automated (lease) |
| Audit log                   | CF Audit Log     | Vault audit log   |
| Dynamic generation          | No               | Yes (DB engine)   |
| Available in Workers env    | Yes (binding)    | Fetch at startup  |
| Works without Kubernetes    | Yes              | Partial           |
| Short-lived credentials     | No               | Yes               |
+-----------------------------+------------------+-------------------+
```

Use `wrangler secret put` for secrets that are intrinsically
bound to the Cloudflare edge (e.g., third-party API keys that
Vault cannot generate). Use Vault for database credentials,
internal service tokens, and anything that benefits from
automatic lease-based rotation.

## 5. TTL, Lease Renewal, and Revocation

```bash
# Renew a lease before it expires
vault lease renew database/creds/app-role/<lease-id>

# Revoke immediately (incident response)
vault lease revoke database/creds/app-role/<lease-id>

# Revoke all credentials for a role at once
vault lease revoke -prefix database/creds/app-role/

# Inspect remaining TTL
vault token lookup <token>
```

Set `max_ttl` on roles to enforce an upper bound regardless of
how many times the agent renews. Workers deployed to Cloudflare
edges cannot run a sidecar; inject the credential at deploy time
via CI and treat the TTL as the deploy cadence floor (redeploy
before expiry).

## Anti-patterns

- Committing a Vault root token to `.env` or Kubernetes secrets.
  Use AppRole or Kubernetes auth; issue role-scoped tokens only.
- Setting `max_ttl` to `0` (unlimited). This defeats the purpose
  of dynamic secrets and leaves Vault managing immortal leases.
- Using the KV secrets engine for database passwords instead of
  the database secrets engine. KV is static; the database engine
  creates unique credentials per request.

## Gotchas

- Vault Agent rewrites the secret file atomically. Applications
  that mmap the file or hold an open file descriptor may not see
  the update. Use inotify-based file watchers or SIGHUP handlers.
- Cloudflare Workers bind secrets at deploy time via
  `wrangler.toml` or `wrangler secret put`. There is no runtime
  call to Vault from the edge. Dynamic rotation requires a redeploy.
- `scram-sha-256` password authentication must be set in
  `connection_url`; md5 is disabled on Postgres 14+ by default.

## Verification

```bash
# Confirm database engine is mounted
vault secrets list | grep database

# Request and verify a credential
vault read database/creds/app-role

# Confirm the Postgres role was created
psql -h pg.internal -U vault_root -c "\du" | grep v-token

# After TTL expiry, confirm the role was dropped
psql -h pg.internal -U vault_root -c "\du" | grep v-token
# (no output expected)
```

## Related

- `kubernetes-secrets-external-operator.md`
- `cloudflare-api-token-scoping.md`
- `vault-pki-mtls-internal-services.md`

## Source URLs (verified 2026-08-17)

- https://developer.hashicorp.com/vault/docs/secrets/databases/postgresql
- https://developer.hashicorp.com/vault/docs/auth/kubernetes
- https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developer.hashicorp.com/vault/docs/concepts/lease
