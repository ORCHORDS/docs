# Cloudflare Workers Account-Level API Token Scoping

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Workers-based automation script uses an account-owner API token.
When the token is rotated or leaked, every Worker and CI pipeline that uses it breaks simultaneously.
The goal is fine-grained API tokens — one per Worker per purpose — so a compromised token has minimal blast radius and rotation is surgical.

## Context

Cloudflare API tokens support permission groups scoped to resources (Account, Zone, or specific sub-resources).
Unlike API Keys (which are bound to the account owner), API tokens can be created programmatically and scoped to the exact permissions a given Worker needs.
Workers that call the Cloudflare API should use a dedicated token stored as a Worker Secret, not an environment variable checked into source control.
This article covers the token permission matrix, token-per-Worker provisioning via the API, and runtime verification patterns.

## Cloudflare Permission Groups Reference for Workers

```typescript
// Common permission groups needed by Workers integrations:
const PERMISSION_GROUPS = {
  // DNS automation Workers
  dns_write:          'e086da7e2179491d91ee5f35b3ca777a', // DNS:Edit
  dns_read:           '82e64a83756745bbbb1c9c2701bf816b', // DNS:Read

  // Workers deployment pipelines
  workers_scripts:    '1a71c399035c4006a1de62c6ec4ca8ad', // Workers Scripts:Edit
  workers_routes:     '9a27d8e59e394de78f2bc89efd8d88c2', // Workers Routes:Edit

  // Access provisioning Workers
  access_edit:        'ed07f6c337da4195b4e72a1fb2c6bcae', // Access: Apps and Policies:Edit

  // Analytics Workers
  analytics_read:     'c1fde68c7bcc44588cbb6ddbc16d6480', // Account Analytics:Read

  // R2 Workers
  r2_edit:            '6a018a9f2fc74eb6af07c90a5a0aed4d', // Workers R2 Storage:Edit
  r2_read:            '0e13ca39a0ee4d85ba6038bf9c32e4ca', // Workers R2 Storage:Read
} as const;
```

## Creating a Scoped Token via API from a Worker

```typescript
// Provisioner: creates a scoped token for a new Worker deployment
export interface Env {
  CF_ACCOUNT_ID: string;
  CF_PROVISIONER_TOKEN: string; // must have: API Tokens:Edit
}

interface TokenRequest {
  worker_name: string;
  permissions: Array<{ id: string; type: 'read' | 'edit' }>;
  ttl_days?: number;
}

async function createWorkerToken(req: TokenRequest, env: Env): Promise<{ token: string; id: string }> {
  const expiry = req.ttl_days
    ? new Date(Date.now() + req.ttl_days * 86400 * 1000).toISOString()
    : undefined;

  const body: Record<string, unknown> = {
    name: `worker-${req.worker_name}-${Date.now()}`,
    policies: [
      {
        effect: 'allow',
        resources: {

        },
        permission_groups: req.permissions.map(p => ({ id: p.id, name: '' })),
      },
    ],
  };

  if (expiry) body['not_before'] = new Date().toISOString();
  if (expiry) body['expires_on'] = expiry;

  const res = await fetch('https://api.cloudflare.com/client/v4/user/tokens', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CF_PROVISIONER_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  const data = await res.json() as any;
  if (!data.success) throw new Error(JSON.stringify(data.errors));
  return { token: data.result.value, id: data.result.id };
}
```

## Runtime Token Verification in a Worker

```typescript
// Verify that the token a Worker uses is still valid before making API calls
async function verifyToken(token: string): Promise<boolean> {
  const res = await fetch('https://api.cloudflare.com/client/v4/user/tokens/verify', {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json() as any;
  return data.result?.status === 'active';
}

// Use in Worker fetch handler with circuit-breaker pattern
export default {
  async fetch(_req: Request, env: Env): Promise<Response> {
    const valid = await verifyToken(env.CF_API_TOKEN);
    if (!valid) {
      // Emit metric and return degraded response — do not expose token status to caller
      console.error('CF_API_TOKEN is inactive or expired');
      return new Response('Service temporarily unavailable', { status: 503 });
    }
    // ... proceed with API calls
    return new Response('OK');
  },
};
```

## Token Rotation via Workers Secrets API

```typescript
// Rotate a Worker's API token secret without redeploying the Worker
async function rotateWorkerSecret(
  workerName: string,
  secretName: string,
  newValue: string,
  env: Env,
): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/workers/scripts/${workerName}/secrets`,
    {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${env.CF_PROVISIONER_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: secretName, text: newValue, type: 'secret_text' }),
    },
  );
  const data = await res.json() as any;
  if (!data.success) throw new Error(`Secret rotation failed: ${JSON.stringify(data.errors)}`);
}
```

## Token Audit: Listing Active Tokens for a Worker

```typescript
async function listAccountTokens(env: Env): Promise<object[]> {
  const res = await fetch('https://api.cloudflare.com/client/v4/user/tokens?per_page=100', {
    headers: { Authorization: `Bearer ${env.CF_PROVISIONER_TOKEN}` },
  });
  const data = await res.json() as any;
  return (data.result ?? [])
    .filter((t: any) => t.name.startsWith('worker-'))
    .map((t: any) => ({
      id: t.id,
      name: t.name,
      status: t.status,
      expires_on: t.expires_on ?? 'never',
      last_used_on: t.last_used_on ?? 'never',
    }));
}
```

## Anti-patterns

- **Single shared API token across all Workers** — a single leak requires rotating every integration simultaneously.
- **Storing tokens in `wrangler.toml` vars** — vars are plaintext in version control; always use `wrangler secret put` or the Secrets API.
- **Not setting token expiry** — permanent tokens accumulate over time; use `expires_on` for automation tokens (30–90 days) and rotate on schedule.
- **Overly broad `resources: '*'`** — always scope to the specific account or zone; avoid granting cross-zone permissions to single-purpose Workers.

## Gotchas

- `user/tokens` API requires the **token used to create it** to have `API Tokens:Edit` permission — this is distinct from all other permission groups.
- Token `value` is only returned **once** at creation; store it immediately in Workers Secrets before the response is discarded.
- Verifying a token via `/user/tokens/verify` consumes one API request against your rate limit; cache the result in a Durable Object or KV with a short TTL (< 5 min) for high-frequency Workers.
- IP filtering on tokens (`condition.request.ip.in`) is not supported for Workers; use Cloudflare Access service tokens for IP-bound scenarios instead.

## Verification

```bash
# List all worker-prefixed tokens
curl -s "https://api.cloudflare.com/client/v4/user/tokens?per_page=100" \
  -H "Authorization: Bearer $CF_PROVISIONER_TOKEN" | jq '[.result[] | select(.name | startswith("worker-"))]'

# Verify a specific token is active
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer $TARGET_TOKEN" | jq '.result.status'

# List secrets on a Worker (names only, not values)
wrangler secret list --name my-worker
```

## Related

- `cloudflare-account-organization-team-access.md`
- `secrets-rotation-runbook.md`
- `workers-secrets-rotation-automation.md`
- `vault-cloudflare-workers-dynamic-secrets.md`

## Sources

- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://developers.cloudflare.com/api/resources/user/subresources/tokens/
- https://developers.cloudflare.com/workers/configuration/secrets/
