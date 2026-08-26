# Workers IP Allowlist + Cloudflare Access JWT Verification

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Worker exposes an internal API that should only be reachable from a set of known CIDR ranges and must also carry a valid Cloudflare Access JWT. A request that passes IP but lacks a valid JWT — or vice-versa — must be rejected with a logged denial in D1 for audit purposes.

---

## Context
Cloudflare injects the true client IP into the `CF-Connecting-IP` header before the request reaches your Worker. CIDR matching is done in-process against a list stored in KV so it can be updated without redeploying. The Access JWT (`Cf-Access-Jwt-Assertion`) is verified against your team's JWKS endpoint using the Web Crypto API — no external library required. All denials are written to a D1 `access_denials` table for SOC-2 trail.

---

## D1 Schema
```sql
CREATE TABLE IF NOT EXISTS access_denials (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  client_ip    TEXT NOT NULL,
  reason       TEXT NOT NULL, -- 'ip_blocked' | 'jwt_missing' | 'jwt_invalid'
  path         TEXT,
  user_email   TEXT,
  denied_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_denials_ip ON access_denials (client_ip, denied_at DESC);
```

## KV CIDR Allowlist format
```typescript
// Store in KV under key "ip_allowlist"
// Value is a JSON array of CIDR strings
// Example: wrangler kv key put --binding=KV ip_allowlist '["10.0.0.0/8","172.16.0.0/12","192.168.1.0/24"]'
type CIDRList = string[]; // ["10.0.0.0/8", "203.0.113.5/32"]
```

## CIDR + JWT Worker
```typescript
// src/access-guard.ts
export interface Env {
  KV: KVNamespace;
  DB: D1Database;
  ACCESS_TEAM_DOMAIN: string; // e.g. "myteam.cloudflareaccess.com"
  ACCESS_AUD: string;          // Application Audience tag from Access dashboard
}

// ---- IP / CIDR helpers ----
function ipToInt(ip: string): number {
  return ip.split('.').reduce((acc, octet) => (acc << 8) | parseInt(octet, 10), 0) >>> 0;
}

function cidrContains(cidr: string, ip: string): boolean {
  const [base, bits] = cidr.split('/');
  const mask = bits ? ~((1 << (32 - parseInt(bits, 10))) - 1) >>> 0 : 0xffffffff;
  return (ipToInt(base) & mask) === (ipToInt(ip) & mask);
}

async function isIpAllowed(ip: string, kv: KVNamespace): Promise<boolean> {
  const raw = await kv.get('ip_allowlist');
  if (!raw) return false;
  const cidrs: string[] = JSON.parse(raw);
  return cidrs.some((cidr) => cidrContains(cidr, ip));
}

// ---- JWT helpers ----
async function fetchJwks(teamDomain: string): Promise<JsonWebKey[]> {
  const url = `https://${teamDomain}/cdn-cgi/access/certs`;
  const resp = await fetch(url);
  const data = await resp.json<{ keys: JsonWebKey[] }>();
  return data.keys;
}

async function verifyJwt(
  token: string,
  jwks: JsonWebKey[],
  aud: string
): Promise<{ email?: string } | null> {
  const [headerB64, payloadB64, sigB64] = token.split('.');
  if (!headerB64 || !payloadB64 || !sigB64) return null;

  const payload = JSON.parse(atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/')));

  // Validate audience and expiry
  const audMatch = Array.isArray(payload.aud)
    ? payload.aud.includes(aud)
    : payload.aud === aud;
  if (!audMatch) return null;
  if (payload.exp < Math.floor(Date.now() / 1000)) return null;

  // Verify signature against each key
  const signingInput = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature = Uint8Array.from(
    atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')),
    (c) => c.charCodeAt(0)
  );

  for (const jwk of jwks) {
    try {
      const key = await crypto.subtle.importKey(
        'jwk',
        jwk,
        { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
        false,
        ['verify']
      );
      const valid = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, signature, signingInput);
      if (valid) return { email: payload.email };
    } catch {
      // try next key
    }
  }
  return null;
}

async function logDenial(
  db: D1Database,
  clientIp: string,
  reason: string,
  path: string,
  userEmail?: string
): Promise<void> {
  await db
    .prepare(
      'INSERT INTO access_denials (client_ip, reason, path, user_email) VALUES (?, ?, ?, ?)'
    )
    .bind(clientIp, reason, path, userEmail ?? null)
    .run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const clientIp = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
    const path = new URL(request.url).pathname;

    // 1. IP check
    const ipOk = await isIpAllowed(clientIp, env.KV);
    if (!ipOk) {
      await logDenial(env.DB, clientIp, 'ip_blocked', path);
      return new Response('Forbidden', { status: 403 });
    }

    // 2. JWT presence
    const jwtToken = request.headers.get('Cf-Access-Jwt-Assertion');
    if (!jwtToken) {
      await logDenial(env.DB, clientIp, 'jwt_missing', path);
      return new Response('Unauthorized', { status: 401 });
    }

    // 3. JWT validation
    const jwks = await fetchJwks(env.ACCESS_TEAM_DOMAIN);
    const claims = await verifyJwt(jwtToken, jwks, env.ACCESS_AUD);
    if (!claims) {
      await logDenial(env.DB, clientIp, 'jwt_invalid', path);
      return new Response('Unauthorized', { status: 401 });
    }

    // Request is authorized — attach email to downstream headers
    const proxied = new Request(request);
    const headers = new Headers(proxied.headers);
    if (claims.email) headers.set('X-Authenticated-Email', claims.email);
    return fetch(new Request(request, { headers }));
  },
};
```

---

## Anti-patterns
- **Trusting `X-Forwarded-For` instead of `CF-Connecting-IP`** — X-Forwarded-For can be spoofed by the client; Cloudflare always sets CF-Connecting-IP to the true outer IP.
- **Caching JWKS indefinitely** — Access rotates keys; cache for at most 5 minutes using a module-level variable or Cache API to avoid stale-key rejections.
- **Logging to an external analytics service inside the critical path** — use `ctx.waitUntil()` for D1 writes so they don't add to response latency.

---

## Gotchas
- IPv6 addresses from CF-Connecting-IP will not match IPv4 CIDRs; your allowlist and matching logic must handle both families or normalise to IPv4-mapped form.
- The `Cf-Access-Jwt-Assertion` header is only injected when traffic passes through a Cloudflare Access application policy; direct Worker invocations will not have it.
- `crypto.subtle` is synchronous in its key import step on some runtimes but async in Workers — always `await` it.

---

## Verification
```bash
# Populate KV allowlist
wrangler kv key put --binding=KV ip_allowlist '["203.0.113.0/24"]'

# Test blocked IP (should return 403)
curl -H "CF-Connecting-IP: 1.2.3.4" https://access-guard.<sub>.workers.dev/

# Test missing JWT (IP in allowlist, should return 401)
curl -H "CF-Connecting-IP: 203.0.113.5" https://access-guard.<sub>.workers.dev/

# Query denial log
wrangler d1 execute <db-name> --command \
  "SELECT * FROM access_denials ORDER BY denied_at DESC LIMIT 10;"
```

---

## Related
- `cloudflare-tunnel-private-network-workers.md`
- `wrangler-ci-secret-rotation-workers.md`

---

## Sources
- Cloudflare Access JWT verification — https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- CF-Connecting-IP header — https://developers.cloudflare.com/fundamentals/reference/http-request-headers/#cf-connecting-ip
- Workers KV — https://developers.cloudflare.com/kv/api/
