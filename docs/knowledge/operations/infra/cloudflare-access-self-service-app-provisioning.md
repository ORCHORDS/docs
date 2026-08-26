# Cloudflare Access Application Self-Service Provisioning

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Platform teams receive constant tickets to add new internal apps behind Cloudflare Access.
Engineers cannot self-serve: they must wait for infra to manually create an Access Application, assign policies, and wire the DNS record.
The goal is a Worker-backed provisioning API that lets developers register new apps on demand with guardrails enforced programmatically.

## Context

Cloudflare Access is part of Zero Trust and protects internal applications via identity-aware reverse proxy.
Each protected app requires an **Access Application** (defines the hostname/path) and one or more **Access Policies** (who can reach it).
Both are managed via the Cloudflare REST API (`/accounts/:id/access/apps`).
A Workers-based provisioner can validate inputs, enforce naming conventions, and call the API using a scoped service token — eliminating human-in-the-loop for routine app onboarding.

## Provisioner Worker Entrypoint

```typescript
// src/provision.ts
export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;       // scoped: Access:Edit + DNS:Edit
  ALLOWED_ZONES: string;      // comma-separated zone IDs
  PROVISIONER_SECRET: string; // HMAC secret for caller auth
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const sig = req.headers.get('x-provisioner-sig') ?? '';
    const body = await req.text();
    if (!(await verifyHmac(sig, body, env.PROVISIONER_SECRET))) {
      return new Response('Unauthorized', { status: 401 });
    }

    const payload: ProvisionRequest = JSON.parse(body);
    const result = await provisionApp(payload, env);
    return Response.json(result, { status: result.ok ? 201 : 400 });
  },
};
```

## Input Validation and Naming Guardrails

```typescript
interface ProvisionRequest {
  subdomain: string;    // e.g. "myapp"
  zone_id: string;
  team_email_domain: string; // e.g. "example.com"
  session_duration: string;  // e.g. "8h"
}

function validateRequest(p: ProvisionRequest): string | null {
  if (!/^[a-z0-9-]{3,40}$/.test(p.subdomain))
    return 'subdomain must be 3-40 lowercase alphanumeric or hyphen chars';
  const allowedZones = (globalThis as any).env?.ALLOWED_ZONES?.split(',') ?? [];
  if (!allowedZones.includes(p.zone_id))
    return `zone_id ${p.zone_id} not in allowlist`;
  if (!['1h', '4h', '8h', '24h'].includes(p.session_duration))
    return 'session_duration must be one of: 1h, 4h, 8h, 24h';
  return null;
}
```

## Creating the Access Application via API

```typescript
async function provisionApp(p: ProvisionRequest, env: Env) {
  const err = validateRequest(p);
  if (err) return { ok: false, error: err };

  const domain = `${p.subdomain}.internal.example.com`;
  const headers = {
    'Authorization': `Bearer ${env.CF_API_TOKEN}`,
    'Content-Type': 'application/json',
  };
  const base = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}`;

  // 1. Create Access Application
  const appRes = await fetch(`${base}/access/apps`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      name: p.subdomain,
      domain,
      type: 'self_hosted',
      session_duration: p.session_duration,
      auto_redirect_to_identity: true,
      allowed_idps: [],          // inherits account IdPs
    }),
  });
  const app = (await appRes.json() as any).result;

  // 2. Attach email-domain policy
  await fetch(`${base}/access/apps/${app.id}/policies`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      name: 'team-members',
      decision: 'allow',
      include: [{ email_domain: { domain: p.team_email_domain } }],
      precedence: 1,
    }),
  });

  return { ok: true, app_id: app.id, domain };
}
```

## HMAC Request Verification

```typescript
async function verifyHmac(sig: string, body: string, secret: string): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify'],
  );
  const sigBytes = hexToBytes(sig);
  const bodyBytes = new TextEncoder().encode(body);
  return crypto.subtle.verify('HMAC', key, sigBytes, bodyBytes);
}

function hexToBytes(hex: string): Uint8Array {
  const arr = new Uint8Array(hex.length / 2);
  for (let i = 0; i < arr.length; i++)
    arr[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return arr;
}
```

## Listing Provisioned Apps for Audit

```typescript
// GET /apps — returns all self-hosted Access apps for review
async function listApps(env: Env): Promise<object[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/access/apps?type=self_hosted`,
    { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } },
  );
  const data = await res.json() as any;
  return (data.result ?? []).map((a: any) => ({
    id: a.id,
    name: a.name,
    domain: a.domain,
    session_duration: a.session_duration,
    created_at: a.created_at,
  }));
}
```

## Anti-patterns

- **Using account-owner API token** — the provisioner token must be scoped to Access:Edit and DNS:Edit only; avoid global tokens.
- **No input validation** — without subdomain validation, attackers can provision wildcard or conflicting domains.
- **Skipping policy attachment** — an Access Application with no policy defaults to `deny all`, breaking the newly registered service immediately.
- **Hardcoding team email domain** — domains should be caller-supplied but validated against an allowlist, not hardcoded.

## Gotchas

- Access Application `domain` must match the DNS record that Cloudflare proxies; the provisioner must also create or update the DNS CNAME if it doesn't exist.
- `session_duration` is per-application and overrides the IdP token lifetime — set it conservatively for internal tools.
- The Cloudflare API returns 409 if an app with the same domain already exists; idempotent provisioners should `GET` first or handle 409 gracefully.
- Access Application creation is eventually consistent; DNS changes may take up to 60 seconds to be recognized by the proxy.

## Verification

```bash
# Provision a new app
curl -X POST https://provision.workers.example.com/ \
  -H "x-provisioner-sig: $(echo -n '{"subdomain":"myapp",...}' | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $2}')" \
  -H "Content-Type: application/json" \
  -d '{"subdomain":"myapp","zone_id":"abc123","team_email_domain":"example.com","session_duration":"8h"}'

# Confirm app exists
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/access/apps?type=self_hosted" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | select(.name=="myapp")'
```

## Related

- `cloudflare-zero-trust-staging-prod-isolation.md`
- `cloudflare-account-organization-team-access.md`
- `cloudflare-workers-api-token-scoping.md`
- `vault-cloudflare-workers-dynamic-secrets.md`

## Sources

- https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/
- https://developers.cloudflare.com/cloudflare-one/policies/access/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
