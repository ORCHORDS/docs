# Cloudflare Access Service Token Rotation Outage

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

All machine-to-machine traffic between an internal microservice and a
Cloudflare Access-protected origin dropped to zero at 03:14 UTC. The origin
returned 403 "forbidden" for every request. Human users accessing the same
origin through the browser SSO flow were unaffected. Investigation revealed
that a service token used by the calling microservice had been rotated
manually by a team member who did not realize it was also used by three other
services. Two of the three services had cached the old token in environment
variables and continued presenting invalid credentials for six hours before the
last downstream service was discovered and updated.

---

## Context

Cloudflare Access allows non-human callers (services, CI pipelines, automated
jobs) to authenticate to Access-protected applications using **service tokens**:
a `CF-Access-Client-Id` and `CF-Access-Client-Secret` header pair. Service
tokens are scoped to specific Access applications and have an expiry date.

Unlike browser-based JWT tokens (which Access mints fresh per-session), service
tokens are long-lived credentials that must be actively rotated. When a service
token is rotated in the Cloudflare dashboard, the old token is immediately
invalidated and any caller still presenting it receives a 403.

The incident combined three failure modes:
1. A service token shared across multiple callers with no inventory of which
   callers depended on it.
2. No automated rotation process — the rotation was performed manually and
   inconsistently.
3. Token values stored directly in environment variables rather than a secrets
   manager, making discovery of stale copies difficult.

---

## Service Token Lifecycle

```
Create token in Cloudflare dashboard
    │
    ▼
Distribute Client ID + Secret to callers
    │
    ▼
Token used in Authorization headers for M2M traffic
    │
    ▼
Token approaches expiry (or manual rotation triggered)
    │
    ▼
New token generated ──► Old token invalidated immediately
    │
    ▼
All callers must update within rotation window (0 seconds without grace period)
```

Cloudflare Access service tokens have **no overlap/grace period** by default.
The old token becomes invalid the instant the new one is created (if the
rotation is done by replacing the token rather than creating a new one
alongside the old one).

---

## Correct Rotation Procedure

### Step 1: Create a new token without deleting the old one

In the Cloudflare dashboard, create a **new** service token for the
application. Do not yet delete the old token. The application policy should
accept both tokens (multiple service tokens can be granted access to the same
application policy).

```bash
# Via Cloudflare API — create new service token alongside the old one
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/service_tokens" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-service-2026-08",
    "duration": "8760h"
  }'
```

### Step 2: Update all callers to use the new token

Update secrets in all callers sequentially. Confirm each caller is
successfully authenticating with the new token before proceeding to the next.

```typescript
// Workers caller pattern — pull token from env, never hardcode
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstreamRequest = new Request("https://internal-service.example.com/api/data", {
      headers: {
        "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
      },
    });
    return fetch(upstreamRequest);
  },
};
```

The token must be stored in Workers Secrets (not `wrangler.toml` vars):

```bash
wrangler secret put CF_ACCESS_CLIENT_ID
wrangler secret put CF_ACCESS_CLIENT_SECRET
```

### Step 3: Verify all callers are using the new token

Monitor the Cloudflare Access logs for requests authenticated with the old
Client ID. Zero traffic on the old Client ID is the signal that migration is
complete.

### Step 4: Delete the old token

Only after confirming zero traffic on the old token, delete it from the
Cloudflare dashboard or via API.

```bash
curl -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/service_tokens/${OLD_TOKEN_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"
```

---

## Automation: Token Rotation Without Downtime

For teams rotating tokens on a schedule, a Cloudflare Worker + KV can
orchestrate zero-downtime rotation:

```typescript
// rotation-orchestrator/src/index.ts
import type { Env } from "./types";

interface ServiceToken {
  id: string;
  clientId: string;
  clientSecret: string;
  expiresAt: string;
}

export default {
  // Triggered by a cron: "0 2 * * 1" (weekly at 02:00 UTC on Mondays)
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const currentToken = await env.KV.get<ServiceToken>("current-service-token", {
      type: "json",
    });

    if (!currentToken) {
      console.error("No current service token found in KV — manual setup required");
      return;
    }

    // Create a new token via Cloudflare API
    const newToken = await createServiceToken(env);

    // Write new token to KV — all callers reading from KV will pick it up
    await env.KV.put("current-service-token", JSON.stringify(newToken));

    // Schedule old token deletion after a grace period (callers have 1 hour)
    await env.KV.put("pending-deletion-token-id", currentToken.id, {
      expirationTtl: 3600,
    });

    // Trigger deletion worker via queue
    await env.ROTATION_QUEUE.send({
      action: "delete-old-token",
      tokenId: currentToken.id,
      deleteAfterEpoch: Date.now() + 3600_000,
    });

    console.log(`Token rotation initiated. New token ID: ${newToken.id}`);
  },
};

async function createServiceToken(env: Env): Promise<ServiceToken> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/access/service_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: `service-token-${new Date().toISOString().slice(0, 10)}`,
        duration: "8760h",
      }),
    },
  );

  if (!res.ok) {
    throw new Error(`Failed to create service token: ${res.status}`);
  }

  const data = await res.json<{ result: ServiceToken }>();
  return data.result;
}
```

Callers read the current token from KV at request time (with a short
module-scope cache TTL):

```typescript
// Caller: always fetch token from KV rather than hardcoding in env
let tokenCache: { value: ServiceToken; expiresAt: number } | null = null;

async function getServiceToken(env: Env): Promise<ServiceToken> {
  if (tokenCache && tokenCache.expiresAt > Date.now()) {
    return tokenCache.value;
  }
  const token = await env.KV.get<ServiceToken>("current-service-token", {
    type: "json",
  });
  if (!token) throw new Error("No service token available");
  tokenCache = { value: token, expiresAt: Date.now() + 60_000 }; // 60s cache
  return token;
}
```

---

## Anti-patterns

- Sharing one service token across multiple callers without an inventory.
- Storing token values as `vars` in `wrangler.toml` (committed to source
  control) instead of Workers Secrets.
- Rotating a token without first inventorying all callers — guaranteed outage.
- Deleting a token simultaneously with creating the replacement, leaving no
  overlap window.
- Manual rotation with no runbook and no automation — human error under time
  pressure causes mistakes.
- Ignoring the token expiry date. Access will invalidate an expired token the
  same way it invalidates a deleted one — sudden 403s at the expiry moment.

---

## Gotchas

**Access logs are the only authoritative source of which callers use a token**:
Cloudflare Access logs (via Logpush) record the Client ID of every
authenticated service request. Before rotating, export the last 30 days of
Access logs and grep for the Client ID to find all callers.

**Workers Secrets propagation delay**: After running `wrangler secret put`,
the new secret value takes up to 30 seconds to propagate to all edge nodes.
Do not delete the old token immediately after updating secrets — wait for the
propagation window.

**Service token scope is per-application**: A service token is bound to a
specific Access application. If you protect a second origin with the same
Access policy, the service token does not automatically grant access to the
new origin — you must explicitly add it.

**Expiry is set at creation time**: Service tokens have a `duration` parameter
set when they are created. You cannot extend an existing token's expiry — you
must rotate to a new token with a new expiry.

---

## Verification

1. After completing rotation, confirm zero requests authenticated with the old
   Client ID appear in Access logs for 30 minutes.
2. Run a synthetic monitor every 5 minutes that makes an authenticated M2M
   request and alerts if the response is not 200.
3. Set a calendar reminder (or use the rotation orchestrator's cron) 30 days
   before each service token's expiry date.
4. Maintain a service token inventory in the team wiki: token name, Client ID
   prefix (not full secret), expiry date, owning team, list of callers.

---

## Related

- `zero-trust-access-misconfiguration-outage.md` — Access policy errors
- `workers-secrets-propagation-delay-auth-incident.md` — secrets propagation
- `rotate-credentials-after-every-breach.md` — credential rotation discipline
- `certificate-expiry-outage.md` — expiry-driven outages

---

## Sources

- Cloudflare Zero Trust documentation: "Service tokens"
- Cloudflare Access documentation: "Service auth"
- Cloudflare API reference: `/accounts/{id}/access/service_tokens`
- Cloudflare Zero Trust documentation: "Access logs via Logpush"
