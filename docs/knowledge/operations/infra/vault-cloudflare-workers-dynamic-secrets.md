# HashiCorp Vault Dynamic Secrets for Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Cloudflare Workers that connect to databases or downstream APIs need credentials, but embedding
long-lived secrets in Workers Secrets leaks a broad blast radius if any secret is ever exposed.
The goal is for each Worker invocation to fetch short-lived, automatically-rotated credentials
from HashiCorp Vault so that a leaked token expires in minutes rather than existing indefinitely.

## Context

HashiCorp Vault's dynamic secrets engine generates time-bounded credentials on demand and revokes
them automatically when the lease expires. Workers cannot run a local Vault agent, so the fetch
must happen over HTTPS from inside the Worker request handler. The standard pattern is to store
only a Vault token (or AppRole secret-id) in Workers Secrets, then call the Vault HTTP API at
cold-start to obtain a short-lived database credential or cloud API key. For write-heavy paths
where the cold-start latency matters, a Durable Object can cache the current lease and refresh it
before expiry, keeping the hot path free from Vault round-trips.

## Fetching a Dynamic PostgreSQL Credential at Worker Start

Store `VAULT_ADDR` and `VAULT_TOKEN` (or a renewable AppRole token) as Workers Secrets via
`wrangler secret put`. The Worker requests a credential from the database secrets engine:

```typescript
interface Env {
  VAULT_ADDR: string;
  VAULT_TOKEN: string;
  DB_ROLE: string; // e.g. "app-readonly"
}

interface VaultDBCreds {
  username: string;
  password: string;
  lease_id: string;
  lease_duration: number; // seconds
}

async function fetchVaultDBCreds(env: Env): Promise<VaultDBCreds> {
  const url = `${env.VAULT_ADDR}/v1/database/creds/${env.DB_ROLE}`;
  const res = await fetch(url, {
    method: "GET",
    headers: {
      "X-Vault-Token": env.VAULT_TOKEN,
      "Content-Type": "application/json",
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Vault credential fetch failed ${res.status}: ${body}`);
  }

  const json = (await res.json()) as { data: VaultDBCreds; lease_id: string; lease_duration: number };
  return {
    username: json.data.username,
    password: <redacted-secret>
    lease_id: json.lease_id,
    lease_duration: json.lease_duration,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Fetch fresh credential on each cold start; Durable Object handles caching (see below)
    const creds = await fetchVaultDBCreds(env);

    // Use creds.username + creds.password to connect to Hyperdrive or direct PG over TCP proxy
    // ...
    return new Response(`Connected as ${creds.username}`, { status: 200 });
  },
};
```

## Caching Vault Leases in a Durable Object

Calling Vault on every request adds ~50–200 ms. A Durable Object holds the current credential
in memory and renews the lease proactively before it expires, so warm requests skip Vault entirely:

```typescript
// vault-lease-cache.ts  — Durable Object
export class VaultLeaseCache implements DurableObject {
  private creds: VaultDBCreds | null = null;
  private expiresAt = 0;

  constructor(private readonly state: DurableObjectState, private readonly env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();
    const refreshThreshold = 60_000; // renew 60 s before expiry

    if (!this.creds || now >= this.expiresAt - refreshThreshold) {
      this.creds = await fetchVaultDBCreds(this.env);
      this.expiresAt = now + this.creds.lease_duration * 1000;
    }

    return Response.json(this.creds);
  }
}

// In the main Worker:
async function getCachedCreds(env: Env & { VAULT_CACHE: DurableObjectNamespace }): Promise<VaultDBCreds> {
  const id = env.VAULT_CACHE.idFromName("singleton");
  const stub = env.VAULT_CACHE.get(id);
  const res = await stub.fetch("https://vault-cache/creds");
  return res.json<VaultDBCreds>();
}
```

`wrangler.toml` binding:

```toml
[[durable_objects.bindings]]
name = "VAULT_CACHE"
class_name = "VaultLeaseCache"

[[migrations]]
tag = "v1"
new_classes = ["VaultLeaseCache"]
```

## AppRole Authentication — Avoiding Long-Lived Root Tokens

Using a root or long-lived token in Workers Secrets defeats the purpose. Use Vault AppRole so the
Worker exchanges a short-lived `secret_id` for a renewable token at boot:

```typescript
interface AppRoleAuth {
  role_id: string;
  secret_id: string; // rotated externally; injected via Workers Secret
}

async function vaultLogin(env: Env & AppRoleAuth): Promise<string> {
  const res = await fetch(`${env.VAULT_ADDR}/v1/auth/approle/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role_id: env.role_id,
      secret_id: env.secret_id,
    }),
  });

  if (!res.ok) throw new Error(`AppRole login failed: ${res.status}`);
  const json = (await res.json()) as { auth: { client_token: string } };
  return json.auth.client_token;
}
```

Rotate the `secret_id` from a GitHub Actions pipeline using `vault write -f auth/approle/role/app/secret-id`
and push the new value with `wrangler secret put VAULT_SECRET_ID`.

## Workers Secrets Store vs Vault — Decision Matrix

| Criterion | Workers Secrets Store | Vault Dynamic Secrets |
|---|---|---|
| Credential lifetime | Until manually rotated | Minutes to hours, auto-revoked |
| Blast radius | All Workers sharing the secret | Single lease, single invocation |
| Latency overhead | 0 ms (injected at boot) | 50–200 ms (Vault HTTP round-trip) |
| Audit trail | None built-in | Full Vault audit log per lease |
| Best for | Static API keys, long-lived tokens | Database passwords, cloud credentials |
| Operational complexity | Low | High (Vault cluster required) |

For static third-party API keys that rotate quarterly, Workers Secrets Store is the right answer.
For database credentials or AWS IAM credentials that must rotate automatically, Vault wins.

## Zero-Trust Secret Delivery Pattern

Combine Cloudflare Zero Trust with Vault for a fully zero-trust pipeline:

1. Worker authenticates to Vault via AppRole (role_id in code, secret_id in Workers Secrets).
2. Vault issues a short-lived DB credential (TTL: 15 min).
3. Worker connects to Hyperdrive (connection pooler) using the dynamic credential.
4. Vault audit log records every lease issuance with the AppRole entity.
5. GitHub Actions rotates the AppRole `secret_id` on every deploy via OIDC → Vault JWT auth.

```typescript
// Full zero-trust bootstrap in one async function
async function bootstrap(env: Env): Promise<{ username: string; password: string }> {
  // Step 1: Exchange AppRole for short-lived Vault token
  const vaultToken = await vaultLogin(env);

  // Step 2: Use token to fetch DB creds
  const credRes = await fetch(`${env.VAULT_ADDR}/v1/database/creds/${env.DB_ROLE}`, {
    headers: { "X-Vault-Token": vaultToken },
  });
  const { data } = (await credRes.json()) as { data: { username: string; password: string } };
  return data;
}
```

## Anti-patterns

- Storing a root Vault token in Workers Secrets — a compromised Worker exposes your entire Vault.
- Calling Vault on every request without a Durable Object cache — 200 ms per request compounds to
  significant p99 latency degradation at scale.
- Setting Vault lease TTLs longer than 1 hour for database credentials — the longer the window,
  the larger the exposure if a lease is somehow captured.
- Putting the Vault address in `wrangler.toml` as a plaintext `[vars]` entry when the Vault is
  internal-only — use a secret so it is not exposed in wrangler config committed to source control.
- Ignoring Vault lease revocation on Worker shutdown — Workers have no shutdown hook, so rely on
  Vault's max-TTL and periodic revocation jobs rather than explicit Worker-side cleanup.

## Gotchas

- Vault's default Postgres dynamic-secrets role requires `CREATE ROLE` privilege; the Vault
  database plugin creates a new Postgres user per lease. Confirm `pg_hba.conf` allows connections
  from the Worker's egress IPs (or use Hyperdrive's fixed egress CIDRs).
- The Workers runtime imposes a 30-second CPU time limit per request. If the Vault round-trip
  plus query execution exceeds this, the Worker is killed. Keep Vault TTL negotiation out of the
  hot path using the Durable Object cache pattern.
- Vault HA with Raft replication: if the Vault leader fails mid-request, the Worker will receive a
  503. Add retry logic with exponential back-off and jitter.
- `X-Vault-Request: true` header is required when using Vault Agent Proxy — include it even on
  direct calls to avoid misconfigured proxy rejections.

## Verification

```bash
# Smoke-test Vault reachability from a Worker-equivalent environment
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/database/creds/app-readonly" | jq .

# Check current leases for the app role
vault list sys/leases/lookup/database/creds/app-readonly

# Renew a specific lease
vault lease renew <lease_id>

# Force-revoke all leases for a role (incident response)
vault lease revoke -prefix database/creds/app-readonly

# Confirm Workers Secret is set (does not reveal value)
wrangler secret list --env production
```

## Related

- `infra/secrets-management-vault.md`
- `infra/secrets-management-comparison.md`
- `infra/workers-secrets-rotation-automation.md`
- `infra/cloudflare-durable-objects-stateful-edge.md`
- `infra/pulumi-cloudflare-workers-infrastructure-as-code.md`

## Sources

- https://developer.hashicorp.com/vault/docs/secrets/databases/postgresql
- https://developer.hashicorp.com/vault/docs/auth/approle
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/durable-objects/
- https://developer.hashicorp.com/vault/api-docs/secret/databases
