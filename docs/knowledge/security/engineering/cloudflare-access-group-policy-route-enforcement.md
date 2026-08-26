# Cloudflare Access Per-Group Policy Route Enforcement in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A single application behind Cloudflare Access has routes requiring different levels of membership: `/admin/*` must only be reachable by the `engineering` Access group, `/reports/*` by `billing` or `engineering`, and `/api/*` by any authenticated user. A single catch-all Access policy cannot express this granularity — all groups would see all routes. A Workers middleware that verifies group membership per route is the correct enforcement point.

## Context

Cloudflare Access issues a signed JWT (`CF-Access-Jwt-Assertion` header) after a user authenticates. The JWT payload contains a `groups` claim — an array of group names the user belongs to within the Cloudflare Access organization. Workers can verify this JWT using the Access public keys (JWKS endpoint) and enforce per-route group membership in code. The Access policy itself acts as a broad front gate (any authenticated user); the Workers middleware acts as the fine-grained inner gate.

---

## 1. JWKS Fetching and JWT Verification

```typescript
// src/access-jwt.ts
export interface AccessJwtPayload {
  sub: string;       // user identifier (email or service token ID)
  email?: string;
  groups: string[];  // Cloudflare Access group names
  iat: number;
  exp: number;
  iss: string;
  aud: string[];
}

const JWKS_CACHE = new Map<string, CryptoKey>();

async function fetchPublicKey(teamDomain: string, kid: string): Promise<CryptoKey> {
  const cacheKey = `${teamDomain}:${kid}`;
  if (JWKS_CACHE.has(cacheKey)) return JWKS_CACHE.get(cacheKey)!;

  const resp = await fetch(`https://${teamDomain}/cdn-cgi/access/certs`);
  if (!resp.ok) throw new Error('Failed to fetch Access JWKS');
  const jwks = await resp.json<{ keys: JsonWebKey[] }>();

  // Find the matching key by kid (key ID) in the JWT header
  const jwk = jwks.keys.find((k: any) => k.kid === kid);
  if (!jwk) throw new Error(`No key found for kid=${kid}`);

  const key = await crypto.subtle.importKey(
    'jwk', jwk,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  );
  JWKS_CACHE.set(cacheKey, key);
  return key;
}

export async function verifyAccessJwt(
  token: string,
  teamDomain: string,
  audience: string,
): Promise<AccessJwtPayload> {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Malformed JWT');

  const headerJson = JSON.parse(atob(parts[0].replace(/-/g, '+').replace(/_/g, '/')));
  const publicKey = await fetchPublicKey(teamDomain, headerJson.kid);

  const enc = new TextEncoder();
  const signingInput = enc.encode(`${parts[0]}.${parts[1]}`);
  const signature = Uint8Array.from(
    atob(parts[2].replace(/-/g, '+').replace(/_/g, '/')),
    c => c.charCodeAt(0),
  );

  const valid = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', publicKey, signature, signingInput);
  if (!valid) throw new Error('Invalid JWT signature');

  const payload: AccessJwtPayload = JSON.parse(
    atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')),
  );

  if (payload.exp < Math.floor(Date.now() / 1000)) throw new Error('JWT expired');
  if (!payload.aud.includes(audience)) throw new Error('Invalid audience');

  return payload;
}
```

---

## 2. Route-to-Group Policy Map

```typescript
// src/route-policy.ts

interface RoutePolicy {
  pattern: RegExp;
  requiredGroups: string[][];  // outer = OR, inner = AND (all groups in one inner array must match)
  description: string;
}

// Policies evaluated in order — first match wins
export const ROUTE_POLICIES: RoutePolicy[] = [
  {
    pattern: /^\/admin\//,
    requiredGroups: [['engineering']],   // must be in 'engineering'
    description: 'Admin panel — engineering only',
  },
  {
    pattern: /^\/reports\//,
    requiredGroups: [['billing'], ['engineering']],  // billing OR engineering
    description: 'Reports — billing or engineering',
  },
  {
    pattern: /^\/api\/internal\//,
    requiredGroups: [['engineering'], ['sre']],      // engineering OR sre
    description: 'Internal API — engineering or SRE',
  },
  {
    pattern: /^\/api\//,
    requiredGroups: [[]],   // any authenticated user (empty inner array = no group requirement)
    description: 'Public API — any authenticated user',
  },
];

export function findPolicy(pathname: string): RoutePolicy | null {
  return ROUTE_POLICIES.find(p => p.pattern.test(pathname)) ?? null;
}

export function satisfiesPolicy(userGroups: string[], policy: RoutePolicy): boolean {
  // Any one inner group set must be fully satisfied (OR of ANDs)
  return policy.requiredGroups.some(required =>
    required.every(g => userGroups.includes(g)),
  );
}
```

---

## 3. Workers Middleware — Enforce Per-Route Access

```typescript
// src/index.ts
import { verifyAccessJwt, AccessJwtPayload } from './access-jwt';
import { findPolicy, satisfiesPolicy } from './route-policy';

export interface Env {
  CF_ACCESS_TEAM_DOMAIN: string;   // e.g. "company.cloudflareaccess.com"
  CF_ACCESS_AUDIENCE: string;      // Application AUD tag from Access dashboard
  ORIGIN: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const token = request.headers.get('CF-Access-Jwt-Assertion');

    if (!token) {
      return new Response('Missing Access JWT', { status: 401 });
    }

    let payload: AccessJwtPayload;
    try {
      payload = await verifyAccessJwt(token, env.CF_ACCESS_TEAM_DOMAIN, env.CF_ACCESS_AUDIENCE);
    } catch (err) {
      return new Response(`Access JWT invalid: ${(err as Error).message}`, { status: 401 });
    }

    const policy = findPolicy(url.pathname);
    if (!policy) {
      // No policy defined for this route — deny by default (fail closed)
      return new Response('No access policy defined for this route', { status: 403 });
    }

    if (!satisfiesPolicy(payload.groups, policy)) {
      return new Response(
        JSON.stringify({
          error: 'insufficient_group_membership',
          route: url.pathname,
          policy: policy.description,
          userGroups: payload.groups,
        }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      );
    }

    // Inject authenticated identity headers for origin use
    const upstream = new Request(request, {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        'X-Auth-User': payload.email ?? payload.sub,
        'X-Auth-Groups': payload.groups.join(','),
      }),
    });
    return env.ORIGIN.fetch(upstream);
  },
};
```

---

## 4. Caching Verified Payloads in KV

Verifying a JWT on every request adds latency from JWKS fetching (first cold start). Cache the parsed payload in KV for the JWT's remaining lifetime.

```typescript
// src/jwt-cache.ts
export async function getCachedPayload(
  kv: KVNamespace,
  token: string,
): Promise<AccessJwtPayload | null> {
  // Key on the signature portion (last JWT segment) — unique per issuance
  const sig = token.split('.')[2];
  return kv.get<AccessJwtPayload>(`jwt:${sig}`, 'json');
}

export async function cachePayload(
  kv: KVNamespace,
  token: string,
  payload: AccessJwtPayload,
): Promise<void> {
  const sig = token.split('.')[2];
  const ttl = payload.exp - Math.floor(Date.now() / 1000);
  if (ttl <= 0) return;
  await kv.put(`jwt:${sig}`, JSON.stringify(payload), { expirationTtl: Math.min(ttl, 300) });
}
```

---

## Anti-patterns

- Using only the Cloudflare Access UI policy (single catch-all policy) without per-route Workers enforcement — Access allows or denies the whole application, not individual paths.
- Trusting the `X-Auth-Groups` header from the incoming request instead of deriving it from the verified JWT — clients can forge headers.
- Storing the full JWT as a KV cache key — the key itself becomes a bearer token; store only the signature segment (last `.` split part).
- Returning the user's full group list in 403 responses in production — use generic error messages externally; log details internally.
- Failing open when `findPolicy()` returns `null` — always deny unconfigured routes (principle of least privilege).

## Gotchas

- Cloudflare Access group names are case-sensitive strings from the Access dashboard; `Engineering` and `engineering` are different groups — normalize at source.
- The `groups` claim in Access JWTs contains group **names**, not UUIDs, in the default configuration — verify this matches your Access group setup.
- Service tokens (non-human authenticators) typically have an empty `groups` array; account for this in policies that should allow service tokens through.
- JWKS keys rotate periodically; the in-memory `JWKS_CACHE` (`Map`) is per-isolate and clears on Worker restart — it does not persist across deployments or global PoPs.
- Access JWTs have a default lifetime of 20 minutes; KV cache TTL should be capped well below this to prevent serving stale group membership after group changes.

## Verification

```bash
# Decode Access JWT to inspect groups claim (does not verify signature)
echo $CF_ACCESS_JWT | cut -d. -f2 | base64 -d 2>/dev/null | jq '.groups'

# Test route enforcement
curl -H "CF-Access-Jwt-Assertion: $ENGINEERING_USER_JWT" https://app.example.com/admin/settings
# Expected: 200

curl -H "CF-Access-Jwt-Assertion: $BILLING_USER_JWT" https://app.example.com/admin/settings
# Expected: 403 with insufficient_group_membership

curl -H "CF-Access-Jwt-Assertion: $BILLING_USER_JWT" https://app.example.com/reports/q1
# Expected: 200
```

## Related

- `cloudflare-access-jwt-claims-rbac-workers.md` — JWT claims RBAC (roles/permissions beyond groups)
- `cloudflare-access-jwt-assertion-validation.md` — Low-level JWT assertion verification
- `cloudflare-access-bypass-prevention.md` — Preventing Access policy bypass
- `cloudflare-access-jwt-public-key-rotation-workers.md` — JWKS key rotation handling

## Sources

- [Cloudflare Access JWT Validation](https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/)
- [Access Groups Configuration](https://developers.cloudflare.com/cloudflare-one/policies/access/groups/)
- [Access JWT Payload Reference — groups claim](https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/application-token/)
- [Workers KV — Expiration TTL](https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys)
