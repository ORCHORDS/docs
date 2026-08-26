# IP Allowlist/Blocklist Enforcement Middleware with Cloudflare Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

An internal API or admin panel must only be reachable from known office IP ranges and approved individual addresses. Simultaneously, certain abusive IPs or entire countries need to be blocked without touching origin server configuration. The access list must be updatable at runtime without redeployment.

## Context

Cloudflare Workers receive the real client IP in `request.headers.get('CF-Connecting-IP')` and country code in `request.cf.country`. Workers KV provides a globally distributed, low-latency key-value store ideal for allowlist/blocklist lookups. By storing CIDR blocks and individual IPs in KV, an admin API can update rules in real time and they propagate to all edge locations within seconds.

## Solution

### Step 1 — CIDR Matching Logic

```typescript
// lib/cidr.ts
export function ipToNumber(ip: string): number {
  const parts = ip.split('.').map(Number);
  return ((parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]) >>> 0;
}

export function cidrContains(cidr: string, ip: string): boolean {
  const [networkStr, prefixStr] = cidr.split('/');
  const prefix = parseInt(prefixStr ?? '32', 10);
  const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0;
  const networkNum = ipToNumber(networkStr) & mask;
  const ipNum = ipToNumber(ip) & mask;
  return networkNum === ipNum;
}

// Check an IP against a list of CIDRs and exact IPs
export function matchesAnyRule(rules: string[], ip: string): boolean {
  for (const rule of rules) {
    if (rule.includes('/')) {
      if (cidrContains(rule, ip)) return true;
    } else {
      if (rule === ip) return true;
    }
  }
  return false;
}
```

### Step 2 — KV-backed Rule Store

```typescript
// lib/ruleStore.ts
// KV key schema:
//   allowlist:rules  -> JSON string[] of CIDRs / IPs
//   blocklist:rules  -> JSON string[] of CIDRs / IPs
//   bypass:token:<token> -> userId  (bypass tokens for trusted services)

export async function getAllowlist(kv: KVNamespace): Promise<string[]> {
  const raw = await kv.get('allowlist:rules');
  return raw ? JSON.parse(raw) : [];
}

export async function getBlocklist(kv: KVNamespace): Promise<string[]> {
  const raw = await kv.get('blocklist:rules');
  return raw ? JSON.parse(raw) : [];
}

export async function addToAllowlist(
  kv: KVNamespace,
  entry: string
): Promise<void> {
  const list = await getAllowlist(kv);
  if (!list.includes(entry)) {
    list.push(entry);
    await kv.put('allowlist:rules', JSON.stringify(list));
  }
}

export async function removeFromAllowlist(
  kv: KVNamespace,
  entry: string
): Promise<void> {
  const list = await getAllowlist(kv);
  await kv.put('allowlist:rules', JSON.stringify(list.filter(r => r !== entry)));
}

export async function checkBypassToken(
  kv: KVNamespace,
  token: string
): Promise<string | null> {
  return kv.get(`bypass:token:${token}`);
}
```

### Step 3 — Rate Limit Per IP Tier

```typescript
// lib/rateLimit.ts
export type IpTier = 'allowlisted' | 'standard' | 'suspicious';

const RATE_LIMITS: Record<IpTier, number> = {
  allowlisted: 10000,  // requests per minute
  standard: 200,
  suspicious: 20,
};

export async function checkRateLimit(
  kv: KVNamespace,
  ip: string,
  tier: IpTier
): Promise<{ allowed: boolean; remaining: number }> {
  const window = Math.floor(Date.now() / 60000); // 1-minute windows
  const key = `rate:${tier}:${ip}:${window}`;
  const limit = RATE_LIMITS[tier];

  const raw = await kv.get(key);
  const current = raw ? parseInt(raw, 10) : 0;

  if (current >= limit) {
    return { allowed: false, remaining: 0 };
  }

  // Increment — TTL of 120s ensures cleanup even if the minute boundary is missed
  await kv.put(key, String(current + 1), { expirationTtl: 120 });
  return { allowed: true, remaining: limit - current - 1 };
}
```

### Step 4 — Geo-blocking Logic

```typescript
// lib/geo.ts
const BLOCKED_COUNTRIES = new Set<string>([
  // Populate from your compliance requirements
  // 'XX', 'YY',
]);

export function isGeoBlocked(country: string | null | undefined): boolean {
  if (!country) return false;
  return BLOCKED_COUNTRIES.has(country.toUpperCase());
}
```

### Step 5 — Middleware Orchestration

```typescript
// middleware/ipGate.ts
import { matchesAnyRule } from '../lib/cidr';
import { getAllowlist, getBlocklist, checkBypassToken } from '../lib/ruleStore';
import { checkRateLimit, IpTier } from '../lib/rateLimit';
import { isGeoBlocked } from '../lib/geo';

export interface IpGateResult {
  allowed: boolean;
  status?: number;
  reason?: string;
  tier?: IpTier;
}

export async function ipGateMiddleware(
  request: Request,
  kv: KVNamespace
): Promise<IpGateResult> {
  const cf = (request as Request & { cf?: IncomingRequestCfProperties }).cf;
  const ip = request.headers.get('CF-Connecting-IP') ?? '';
  const country = cf?.country;

  // Allow bypass token to skip IP checks (for CI/CD, health checks, etc.)
  const bypassToken = request.headers.get('X-Bypass-Token');
  if (bypassToken) {
    const userId = await checkBypassToken(kv, bypassToken);
    if (userId) {
      const rate = await checkRateLimit(kv, ip, 'allowlisted');
      return rate.allowed
        ? { allowed: true, tier: 'allowlisted' }
        : { allowed: false, status: 429, reason: 'Rate limit exceeded (bypass tier)' };
    }
  }

  // Geo block (applied before allowlist — compliance requirement)
  if (isGeoBlocked(country)) {
    return { allowed: false, status: 403, reason: `Country ${country} is blocked` };
  }

  // Blocklist check
  const blocklist = await getBlocklist(kv);
  if (matchesAnyRule(blocklist, ip)) {
    return { allowed: false, status: 403, reason: 'IP is blocklisted' };
  }

  // Allowlist check
  const allowlist = await getAllowlist(kv);
  if (matchesAnyRule(allowlist, ip)) {
    const rate = await checkRateLimit(kv, ip, 'allowlisted');
    return rate.allowed
      ? { allowed: true, tier: 'allowlisted' }
      : { allowed: false, status: 429, reason: 'Rate limit exceeded (allowlisted tier)' };
  }

  // Default: standard tier rate limit
  const rate = await checkRateLimit(kv, ip, 'standard');
  return rate.allowed
    ? { allowed: true, tier: 'standard' }
    : { allowed: false, status: 429, reason: 'Rate limit exceeded' };
}
```

### Step 6 — Admin API for Rule Management

```typescript
// handlers/adminApi.ts
import { addToAllowlist, removeFromAllowlist } from '../lib/ruleStore';

export async function handleAdminApi(
  request: Request,
  kv: KVNamespace,
  adminSecret: string
): Promise<Response> {
  // Authenticate admin requests
  const auth = request.headers.get('Authorization');
  if (auth !== `Bearer ${adminSecret}`) {
    return new Response('Unauthorized', { status: 401 });
  }

  const url = new URL(request.url);
  const body = await request.json<{ entry: string }>();

  if (url.pathname === '/admin/allowlist/add' && request.method === 'POST') {
    await addToAllowlist(kv, body.entry);
    return Response.json({ ok: true });
  }

  if (url.pathname === '/admin/allowlist/remove' && request.method === 'POST') {
    await removeFromAllowlist(kv, body.entry);
    return Response.json({ ok: true });
  }

  return new Response('Not Found', { status: 404 });
}
```

### Step 7 — Worker Integration

```typescript
// worker.ts
import { ipGateMiddleware } from './middleware/ipGate';
import { handleAdminApi } from './handlers/adminApi';

interface Env {
  IP_KV: KVNamespace;
  ADMIN_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith('/admin/')) {
      return handleAdminApi(request, env.IP_KV, env.ADMIN_SECRET);
    }

    const gate = await ipGateMiddleware(request, env.IP_KV);
    if (!gate.allowed) {
      return new Response(gate.reason ?? 'Forbidden', { status: gate.status ?? 403 });
    }

    return fetch(request);
  },
};
```

## Implementation Details

- **KV read latency**: KV reads at the edge are typically sub-millisecond. Fetching both allowlist and blocklist adds ~1-2 ms per request — acceptable for a security gate.
- **CIDR math**: Uses unsigned 32-bit integer arithmetic (`>>> 0`) to avoid JavaScript signed integer pitfalls with high IP addresses (e.g., `192.x.x.x`).
- **Rate limit windows**: 1-minute tumbling windows are simple and predictable. Sliding windows require atomic operations not available in KV; use Durable Objects if sliding windows are required.
- **Bypass tokens**: Stored as `bypass:token:<token>` → `<userId>` to allow per-token audit and revocation without rotating the admin secret.
- **Geo compliance**: Geo blocking runs before the allowlist to satisfy regulatory requirements — even an allowlisted IP in a sanctioned country is blocked.

## Anti-patterns

- Do not store the entire allowlist/blocklist as a single large KV value that exceeds 25 MB — paginate or shard by subnet prefix if the list grows very large.
- Do not trust `X-Forwarded-For` for the real IP; use `CF-Connecting-IP` which Cloudflare sets from the actual connection.
- Do not implement the admin API on the same Worker without strong authentication — a misconfigured allowlist can lock out all users.
- Do not use `kv.get` inside a tight loop over many CIDRs; load the list once per request and iterate in memory.
- Do not apply geo-blocking as the sole security control — it is easily bypassed by VPNs; combine with IP allowlisting for sensitive endpoints.

## Gotchas

- Workers KV is eventually consistent with a typical propagation delay of up to 60 seconds. A newly added blocklist entry may not be active globally for up to a minute.
- IPv6 support requires separate matching logic; this implementation handles IPv4 only. Add IPv6 CIDR matching if your services are dual-stack.
- The `request.cf` object is not populated in local `wrangler dev` by default; use `--remote` flag or mock `cf` properties in tests.
- KV `put` operations in the rate limiter add latency; consider batching or using Durable Objects for high-throughput rate limiting.

## Verification

1. Add `192.168.1.0/24` to the allowlist; send a request from `192.168.1.100` — expect `200`.
2. Add `203.0.113.5` to the blocklist; send a request from that IP — expect `403 IP is blocklisted`.
3. Set a geo-blocked country; send a request with a `cf.country` matching it — expect `403`.
4. Exceed the standard tier rate limit (>200 requests/minute) — expect `429`.
5. Send a request with a valid bypass token — expect `200` regardless of IP.

## Related

- `workers-request-signing-hmac.md` — for authenticating the admin API update calls
- `workers-oauth2-pkce-flow.md` — combining IP gating with user-level authentication

## Sources

- Cloudflare Workers Request: https://developers.cloudflare.com/workers/runtime-apis/request/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare IncomingRequestCfProperties: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- RFC 4632 — CIDR: https://datatracker.ietf.org/doc/html/rfc4632
