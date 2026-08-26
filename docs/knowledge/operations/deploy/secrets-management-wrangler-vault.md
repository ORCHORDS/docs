# Secrets Management: Wrangler Secret Put, Vault Dynamic Secrets & Zero-Downtime Rotation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Rotating a secret (API key, DB password, JWT signing key) in example project requires
updating `wrangler secret put`, redeploying the Worker, and hoping no
in-flight request lands in the window where the old secret is gone but the
new Worker is not yet live. Missed rotations accumulate technical debt and
create audit-finding exposure.

## Context

example project (example.com) uses Cloudflare Workers Secrets for runtime credentials.
This article covers three patterns:

1. **Wrangler automation** — scripted `wrangler secret put` with environment
   scoping and CI integration.
2. **Vault dynamic secrets via Workers** — generating short-lived DB credentials
   from HashiCorp Vault (or Vault-compatible APIs) at request time.
3. **Zero-downtime rotation** — double-write/version-aware approach so rotation
   never interrupts live traffic, with KV fallback if the new secret fetch fails.

---

## Pattern 1 — Wrangler Secret Put Automation

### Basic Usage

```bash
# Put a secret non-interactively (value from stdin)
echo "$NEW_API_KEY" | wrangler secret put STRIPE_KEY --name example project-api

# Environment-scoped secret (staging vs production)
echo "$NEW_API_KEY" | wrangler secret put STRIPE_KEY \
  --name example project-api \
  --env production
```

### Rotation Script

```bash
#!/usr/bin/env bash
# scripts/rotate-secret.sh
set -euo pipefail

SECRET_NAME=$1
NEW_VALUE=$2
WORKER_NAME=${3:-example project-api}
ENV=${4:-production}

echo "Rotating $SECRET_NAME on $WORKER_NAME ($ENV)"

# Write new secret — Workers pick it up within ~30 s without re-deploy
echo "$NEW_VALUE" | wrangler secret put "$SECRET_NAME" \
  --name "$WORKER_NAME" \
  --env "$ENV"

echo "Secret updated. Verifying via health endpoint..."
sleep 35  # wait for propagation

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "https://api.example.com/health?probe=secret")
[[ "$STATUS" == "200" ]] || { echo "Health check failed after rotation"; exit 1; }

echo "Rotation verified."
```

### Secrets Inventory Table

| Secret name         | Scope       | Rotation cadence | Owner        |
|---------------------|-------------|-----------------|--------------|
| `STRIPE_KEY`        | production  | 90 days         | payments team|
| `JWT_SECRET`        | all envs    | 180 days        | platform     |
| `DB_PASSWORD`       | production  | 30 days (Vault) | infra        |
| `SENDGRID_API_KEY`  | production  | 90 days         | platform     |
| `INTERNAL_HMAC_KEY` | all envs    | 365 days        | platform     |

---

## Pattern 2 — Vault Dynamic Secrets via Workers

For database passwords, generate short-lived credentials from Vault at request
time instead of storing a long-lived password in Worker Secrets.

### Architecture

```
Client → Cloudflare Worker → Vault (via Service Token) → DB credential (TTL 1h)
                           ↓
                     Use credential for request
                           ↓
                     Lease expires automatically
```

### Vault Client in Worker

```typescript
// src/vault.ts
const VAULT_ADDR  = "https://vault.internal.example.com";
const VAULT_TOKEN = (env: Env) => env.VAULT_TOKEN; // long-lived service token

interface DBCreds {
  username: string;
  password: string;
  lease_id: string;
  lease_duration: number;
}

export async function getDynamicDBCreds(env: Env): Promise<DBCreds> {
  // Check KV cache for an unexpired lease
  const cached = await env.KV.get("vault:db_creds", "json") as DBCreds | null;
  if (cached && cached.lease_duration > 120) {
    return cached;
  }

  // Fetch fresh credentials from Vault
  const resp = await fetch(
    `${VAULT_ADDR}/v1/database/creds/example project-app-role`,
    {
      headers: { "X-Vault-Token": VAULT_TOKEN(env) },
    }
  );

  if (!resp.ok) {
    if (cached) {
      console.warn("Vault unavailable; using cached creds");
      return cached; // KV fallback
    }
    throw new Error(`Vault error: ${resp.status}`);
  }

  const { data, lease_id, lease_duration } = await resp.json();
  const creds: DBCreds = {
    username: data.username,
    password: <redacted-secret>
    lease_id,
    lease_duration,
  };

  // Cache in KV with TTL = lease_duration - 5 min buffer
  const ttl = Math.max(lease_duration - 300, 60);
  await env.KV.put("vault:db_creds", JSON.stringify(creds), {
    expirationTtl: ttl,
  });

  return creds;
}
```

### KV Fallback on Secret Miss

If Vault is unreachable, the Worker falls back to the last valid credential
cached in KV. This prevents a Vault outage from cascading into a example project outage.

```
Vault reachable?
  YES → fetch fresh creds → cache in KV → use
  NO  → KV has unexpired entry? → use cached creds
        KV empty or expired?    → return 503 with Retry-After: 30
```

---

## Pattern 3 — Zero-Downtime Secret Rotation

Worker Secrets propagate globally in ~30 seconds without a re-deploy. However,
during propagation, different edge nodes may hold different values. For secrets
that require both old and new values to be accepted (e.g., JWT signing keys),
use a versioned double-write window.

### Dual-Key JWT Verification

```typescript
// src/auth.ts
import { verify } from "./jwt";

export async function verifyToken(token: string, env: Env): Promise<Payload> {
  // Try current key first
  try {
    return await verify(token, env.JWT_SECRET);
  } catch (e) {
    // During rotation: fall back to previous key
    if (env.JWT_SECRET_PREV) {
      return await verify(token, env.JWT_SECRET_PREV);
    }
    throw e;
  }
}
```

### Rotation Sequence

```
Step 1: Add new key as JWT_SECRET_NEW (separate wrangler secret put)
Step 2: Deploy code that accepts both JWT_SECRET and JWT_SECRET_NEW
Step 3: Wait for all issued tokens signed with old key to expire (or invalidate)
Step 4: Promote JWT_SECRET_NEW → JWT_SECRET
Step 5: Remove JWT_SECRET_PREV binding
```

```bash
# Step 1
echo "$NEW_KEY" | wrangler secret put JWT_SECRET_NEW --name example project-api

# Step 4 (after soak window)
echo "$NEW_KEY"  | wrangler secret put JWT_SECRET      --name example project-api
echo "$OLD_KEY"  | wrangler secret put JWT_SECRET_PREV --name example project-api

# Step 5 (after all old tokens expire)
wrangler secret delete JWT_SECRET_NEW --name example project-api
wrangler secret delete JWT_SECRET_PREV --name example project-api
```

### Rotation Timeline

| Time    | JWT_SECRET     | JWT_SECRET_PREV | Accepted tokens                 |
|---------|---------------|----------------|----------------------------------|
| T+0     | OLD_KEY        | (unset)        | Signed with OLD_KEY              |
| T+1 min | OLD_KEY        | (unset)        | Deploy dual-verify code          |
| T+35 s  | NEW_KEY        | OLD_KEY        | Signed with OLD or NEW           |
| T+2 h   | NEW_KEY        | OLD_KEY        | Old tokens expired (JWT TTL 2 h) |
| T+2.5 h | NEW_KEY        | (deleted)      | Signed with NEW_KEY only         |

---

## Anti-patterns

- **Storing secrets in `[vars]` in `wrangler.toml`** — these are committed to
  source control and visible in plain text in the Cloudflare dashboard.
  Always use `wrangler secret put`.
- **Rotating without a soak window** — writing a new secret and immediately
  deploying leaves in-flight requests using a mix of old and new values on
  different edge nodes during propagation.
- **Single-key JWT rotation** — invalidates all active sessions simultaneously.
  Use dual-key approach (current + previous) during the token TTL window.
- **Fetching Vault creds on every request** — Vault rate limits service token
  calls. Cache credentials in KV with a TTL slightly shorter than the lease.
- **Skipping health verification after rotation** — a typo or encoding error
  in the secret value is silent until requests start failing.

---

## Gotchas

- `wrangler secret put` succeeds immediately but propagates to all edge nodes
  in approximately 30 seconds. Do not run tests immediately after a put.
- Worker Secrets are encrypted at rest with the account's encryption key.
  They are not visible in `wrangler.toml` or `wrangler secret list` output
  (list shows names only, not values).
- Vault dynamic credentials include a Vault lease ID. The Worker is responsible
  for renewing the lease before it expires if the Worker instance is long-lived
  (e.g., Durable Objects). Standard Workers are stateless and leases expire
  naturally.
- `wrangler secret delete` takes effect within the same ~30-second propagation
  window. Do not delete the old key until all edge nodes have the new key
  (verify via logs or analytics).

---

## Verification

```bash
# List current secret names (values not shown)
wrangler secret list --name example project-api --env production

# Test that health endpoint accepts the new secret
curl -s "https://api.example.com/health?probe=secret" \
  -H "Authorization: Bearer $TEST_JWT" | jq .

# Confirm KV cache entry exists after first Vault fetch
wrangler kv:key get --namespace-id=$NS_ID "vault:db_creds" | jq '{username, lease_duration}'
```

---

## Related

- `workers-secrets-rotation-zero-downtime.md`
- `secrets-rotation-deploy-coordination.md`
- `gitops-secrets-management.md`
- `env-binding-precedence.md`
- `ansible-vault-secrets.md`

## Sources

- Cloudflare Workers Secrets — https://developers.cloudflare.com/workers/configuration/secrets/
- Vault database secrets engine — https://developer.hashicorp.com/vault/docs/secrets/databases
- Wrangler secret commands — https://developers.cloudflare.com/workers/wrangler/commands/#secret
- JWT rotation best practices — https://auth0.com/blog/refresh-tokens-what-are-they-and-when-to-use-them/
