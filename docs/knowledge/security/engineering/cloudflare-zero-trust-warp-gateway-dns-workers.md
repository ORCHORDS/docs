# Cloudflare Zero Trust WARP Gateway DNS Filtering with Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your organisation routes employee traffic through Cloudflare WARP + Gateway.
You need a Cloudflare Worker that:
- Enforces per-team DNS resolution policies (allowlist / blocklist) via Gateway DoH.
- Signs every outbound DNS-over-HTTPS request with a service-token so Gateway logs
  the correct identity context.
- Stores allow/block decisions in D1 for post-hoc compliance auditing.
- Rejects unauthenticated callers before the DNS query ever leaves the Worker.

---

## Context

Cloudflare Gateway processes DNS at the network edge.  Workers sit in front of that
layer and can inspect, mutate, or gate DNS requests before they reach Gateway's
resolver.  A Worker acting as a "DNS proxy" receives a DoH request from a WARP client,
validates the caller's JWT (issued by Cloudflare Access), rewrites the upstream URL to
include the organisation's Gateway DoH endpoint, injects the `CF-Access-Client-Id` /
`CF-Access-Client-Secret` headers, and forwards the query.

The pattern is useful when you need:
- Extra validation logic not expressible in Gateway policies alone.
- Audit logs beyond Gateway's 90-day retention.
- Per-request context (e.g. user-role from the Access JWT) influencing which Gateway
  location (and therefore which policy) the query hits.

---

## 1. Verifying the Cloudflare Access JWT

```typescript
// src/auth.ts
import { jwtVerify, createRemoteJWKSet } from 'jose';

const CERTS_URL =
  'https://<team>.cloudflareaccess.com/cdn-cgi/access/certs';

const JWKS = createRemoteJWKSet(new URL(CERTS_URL));

export interface AccessClaims {
  sub: string;         // user email
  groups: string[];    // Access groups
  aud: string[];
}

export async function verifyAccessJwt(
  token: string,
  audience: string,
): Promise<AccessClaims> {
  const { payload } = await jwtVerify(token, JWKS, {
    issuer: `https://<team>.cloudflareaccess.com`,
    audience,
  });

  const groups = (payload['cf-access-groups'] as string[] | undefined) ?? [];
  return { sub: payload.sub as string, groups, aud: payload.aud as string[] };
}
```

Call this in the Worker entry point before any DNS forwarding logic.

---

## 2. Worker Entry Point — Auth Gate

```typescript
// src/index.ts
import { verifyAccessJwt, AccessClaims } from './auth';
import { forwardDoH } from './doh';
import { auditLog } from './audit';

export interface Env {
  DB: D1Database;
  GATEWAY_DOH_URL: string;   // e.g. https://gateway.cloudflare.com/dns-query
  GATEWAY_LOCATION_DOH_URL: string; // per-team endpoint
  CF_ACCESS_CLIENT_ID: string;
  CF_ACCESS_CLIENT_SECRET: string;
  ACCESS_AUD: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Only DoH content-types pass
    const ct = req.headers.get('accept') ?? '';
    if (!ct.includes('application/dns-message') &&
        !ct.includes('application/dns-json')) {
      return new Response('Bad Request', { status: 400 });
    }

    const cfJwt = req.headers.get('Cf-Access-Jwt-Assertion');
    if (!cfJwt) return new Response('Unauthorized', { status: 401 });

    let claims: AccessClaims;
    try {
      claims = await verifyAccessJwt(cfJwt, env.ACCESS_AUD);
    } catch {
      return new Response('Forbidden', { status: 403 });
    }

    return forwardDoH(req, env, claims);
  },
};
```

---

## 3. Forwarding DoH with Service Token Injection

```typescript
// src/doh.ts
import { AccessClaims } from './auth';
import { auditLog } from './audit';

export async function forwardDoH(
  req: Request,
  env: Env,
  claims: AccessClaims,
): Promise<Response> {
  // Choose Gateway location based on group membership
  const isPriority = claims.groups.includes('engineering');
  const upstream = isPriority
    ? env.GATEWAY_LOCATION_DOH_URL
    : env.GATEWAY_DOH_URL;

  // Build the forwarded request, injecting service-token credentials
  const upstreamReq = new Request(upstream, {
    method: req.method,
    headers: new Headers({
      'accept': req.headers.get('accept') ?? 'application/dns-message',
      'content-type': req.headers.get('content-type') ?? 'application/dns-message',
      'CF-Access-Client-Id': env.CF_ACCESS_CLIENT_ID,
      'CF-Access-Client-Secret': env.CF_ACCESS_CLIENT_SECRET,
      // Propagate the user identity so Gateway logs show the email
      'X-Forwarded-User': claims.sub,
    }),
    body: req.method === 'POST' ? req.body : undefined,
  });

  // For GET DoH the query is in ?dns=<base64url>
  if (req.method === 'GET') {
    const url = new URL(req.url);
    const dnsParam = url.searchParams.get('dns');
    if (!dnsParam) return new Response('Bad Request', { status: 400 });
    const upstreamUrl = new URL(upstream);
    upstreamUrl.searchParams.set('dns', dnsParam);
    const getReq = new Request(upstreamUrl.toString(), upstreamReq);
    const resp = await fetch(getReq);
    await auditLog(env, claims.sub, 'GET', dnsParam, resp.status);
    return resp;
  }

  const resp = await fetch(upstreamReq);
  await auditLog(env, claims.sub, 'POST', '', resp.status);
  return resp;
}
```

---

## 4. D1 Audit Logging

```typescript
// src/audit.ts
export async function auditLog(
  env: Env,
  user: string,
  method: string,
  query: string,
  status: number,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO dns_audit (ts, user_email, method, raw_query_b64, gateway_status)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(Date.now(), user, method, query, status)
    .run();
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS dns_audit (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ts             INTEGER NOT NULL,
  user_email     TEXT    NOT NULL,
  method         TEXT    NOT NULL CHECK (method IN ('GET','POST')),
  raw_query_b64  TEXT    NOT NULL DEFAULT '',
  gateway_status INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dns_audit_user ON dns_audit (user_email, ts);
```

---

## 5. Per-Team Blocklist Check Before Forwarding

```typescript
// src/blocklist.ts
export async function isBlocked(
  env: Env,
  groups: string[],
  domainHex: string, // decoded from the DNS wire format
): Promise<boolean> {
  const placeholders = groups.map(() => '?').join(',');
  const result = await env.DB.prepare(
    `SELECT 1 FROM dns_blocklist
     WHERE group_name IN (${placeholders})
       AND domain_hex = ?
     LIMIT 1`,
  )
    .bind(...groups, domainHex)
    .first<{ 1: number }>();

  return result !== null;
}
```

Integrate in `forwardDoH` before `fetch(upstreamReq)`:

```typescript
// Decode the first question from the DNS wire message (POST body)
// This is a simplified parser — production code should use a proper DNS library.
async function extractFirstQuestionHex(body: ReadableStream | null): Promise<string> {
  if (!body) return '';
  const buf = await new Response(body).arrayBuffer();
  return Buffer.from(buf).toString('hex');
}
```

---

## 6. wrangler.toml Bindings

```toml
name = "dns-gateway-proxy"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "dns-audit"
database_id   = "<your-d1-id>"

[vars]
GATEWAY_DOH_URL          = "https://gateway.cloudflare.com/dns-query"
GATEWAY_LOCATION_DOH_URL = "https://<team-id>.cloudflare-gateway.com/dns-query"
ACCESS_AUD               = "<your-access-audience>"

[secrets]
CF_ACCESS_CLIENT_ID     = "..."   # set via wrangler secret put
CF_ACCESS_CLIENT_SECRET = "..."
```

---

## Anti-patterns

- **Forwarding the caller's raw headers to Gateway** — strips CF-Access headers and
  sends the client IP instead of the Worker's identity.  Always reconstruct headers.
- **Logging full DNS wire payloads** — wire format contains the full queried name in
  cleartext; store only a hash or the decoded QNAME if privacy policy demands it.
- **Caching DoH responses in KV without TTL** — DNS TTLs must be respected; stale
  negative answers block legitimate domains.
- **Trusting `X-Forwarded-User` from the client** — always derive identity from the
  verified Access JWT, never from a header the WARP client can spoof.
- **Using the same service token for multiple environments** — rotate per-env and store
  in Workers Secrets, not `[vars]`.

---

## Gotchas

- Gateway DoH enforces a `CF-Access-Client-Id` format — it must be the **service
  token** UUID, not the Access application client ID.
- Workers have a 30-second CPU time limit; DNS wire parsing should be O(1) header reads,
  not full recursive descent.
- D1 `run()` in Cloudflare Workers does **not** block the response — use
  `ctx.waitUntil(auditLog(...))` so audit writes don't add latency.
- The `jose` library's `createRemoteJWKSet` fetches the JWKS on first request; pin the
  Worker's egress to `<team>.cloudflareaccess.com` in your firewall policy.
- Gateway blocks BYOD WARP clients by default; ensure your Access policy targets the
  correct device-posture group.

---

## Verification

```bash
# 1. Confirm JWT validation rejects missing token
curl -s -o /dev/null -w "%{http_code}" \
  -H "accept: application/dns-message" \
  https://dns-gateway-proxy.<account>.workers.dev/dns-query
# Expect: 401

# 2. Confirm authenticated request reaches Gateway
curl -s -o /dev/null -w "%{http_code}" \
  -H "accept: application/dns-message" \
  -H "Cf-Access-Jwt-Assertion: $(get-test-jwt)" \
  "https://dns-gateway-proxy.<account>.workers.dev/dns-query?dns=$(dig +short cloudflare.com | base64url)"
# Expect: 200

# 3. Confirm audit row written
wrangler d1 execute dns-audit \
  --command "SELECT user_email, gateway_status FROM dns_audit ORDER BY ts DESC LIMIT 5"
```

---

## Related

- `cloudflare-access-jwt-assertion-validation.md`
- `cloudflare-zero-trust-mtls-service-auth.md`
- `durable-objects-auth-patterns.md`
- `workers-environment-variable-hygiene.md`

---

## Sources

- Cloudflare Gateway DoH documentation: https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/
- RFC 8484 — DNS Queries over HTTPS: https://www.rfc-editor.org/rfc/rfc8484
- Cloudflare Access Service Tokens: https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- `jose` npm library: https://github.com/panva/jose
