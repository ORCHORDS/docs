# Workers IP Allowlist Enforcement with KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An internal admin API or a webhook receiver should only accept requests from a known
set of IP addresses. You need to enforce that list at the edge — before any business
logic runs — without a full redeploy each time the list changes.

## Context

Cloudflare Workers KV is the right store for an IP allowlist: reads are fast (sub-ms
from most PoPs), writes propagate globally in under 60 seconds, and the list can be
updated via the REST API or the Dashboard with no code change. The Worker reads the
list on every request, checks whether the caller's IP is present, and rejects with
403 if not. CIDR range support requires a small range-matching helper because KV is
a flat key-value store.

Use WAF Custom Rules instead when the allowlist is static and managed by the platform
team. Use Workers KV when the list is dynamic and owned by the application.

---

## KV structure

Store the allowlist as a single JSON value under a well-known key, not as one key per IP.
This avoids per-IP KV reads and keeps the list atomic.

```
namespace: IP_ALLOWLIST
key:       "admin-api"
value:     {"ips":["203.0.113.10","198.51.100.0/24"],"updatedAt":1724400000000}
```

An optional per-endpoint key scheme (`admin-api`, `webhook-receiver`) lets you maintain
separate lists without a namespace per endpoint.

---

## Parsing and matching IPs

```typescript
interface AllowlistEntry {
  ips: string[];
  updatedAt: number;
}

function ipToInt(ip: string): number {
  const parts = ip.split('.').map(Number);
  return ((parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]) >>> 0;
}

function isIpAllowed(callerIp: string, allowlist: string[]): boolean {
  const callerInt = ipToInt(callerIp);
  for (const entry of allowlist) {
    if (entry.includes('/')) {
      // CIDR notation
      const [base, bits] = entry.split('/');
      const mask = bits === '0' ? 0 : (~0 << (32 - Number(bits))) >>> 0;
      if ((ipToInt(base) & mask) === (callerInt & mask)) return true;
    } else {
      // Exact match
      if (entry === callerIp) return true;
    }
  }
  return false;
}
```

This handles IPv4 CIDR ranges and exact addresses. For IPv6 support, see the Gotchas
section.

---

## Loading the allowlist from KV with in-process caching

```typescript
interface Env {
  IP_ALLOWLIST: KVNamespace;
}

// Module-level cache — lives for the isolate lifetime (typically minutes)
let allowlistCache: AllowlistEntry | null = null;
let cacheLoadedAt = 0;
const CACHE_TTL_MS = 30_000;  // 30 s; KV propagates in ≤ 60 s

async function getAllowlist(
  kv: KVNamespace,
  listKey: string,
): Promise<AllowlistEntry | null> {
  const now = Date.now();
  if (allowlistCache && now - cacheLoadedAt < CACHE_TTL_MS) {
    return allowlistCache;
  }
  const raw = await kv.get(listKey, 'json') as AllowlistEntry | null;
  if (raw) {
    allowlistCache = raw;
    cacheLoadedAt = now;
  }
  return raw;
}
```

The 30-second in-process cache avoids a KV read on every request while still picking
up list updates within ~90 seconds end-to-end (60 s KV propagation + 30 s cache TTL).

---

## Middleware: enforcing the allowlist

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only enforce on admin paths
    if (url.pathname.startsWith('/admin') || url.pathname.startsWith('/webhook')) {
      const callerIp = request.headers.get('CF-Connecting-IP') ?? '';

      const allowlist = await getAllowlist(env.IP_ALLOWLIST, 'admin-api');
      if (!allowlist) {
        // Fail-closed: if the list cannot be loaded, deny the request
        console.error('IP allowlist not found in KV');
        return new Response('Service unavailable', { status: 503 });
      }

      if (!callerIp || !isIpAllowed(callerIp, allowlist.ips)) {
        // Log for audit without revealing the list contents
        console.warn(`IP blocked: ${callerIp} on ${url.pathname}`);
        return new Response('Forbidden', { status: 403 });
      }
    }

    return handleRequest(request, env);
  },
};
```

`CF-Connecting-IP` is set by Cloudflare and reflects the true client IP after any proxy
stripping — do not use `X-Forwarded-For` for enforcement.

---

## Updating the allowlist via the Cloudflare REST API

```bash
# Add a new IP range to the admin-api allowlist
CURRENT=$(curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces/$KV_NAMESPACE_ID/values/admin-api" \
  -H "Authorization: Bearer $CF_API_TOKEN")

# Merge and write back (example using jq)
echo "$CURRENT" | jq '.ips += ["192.0.2.50"]' | \
  curl -X PUT "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces/$KV_NAMESPACE_ID/values/admin-api" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @-
```

Automate this via a GitHub Actions workflow or a Terraform `cloudflare_workers_kv` resource.

---

## Logging blocked requests to Workers Analytics Engine

```typescript
interface Env {
  IP_ALLOWLIST: KVNamespace;
  AE: AnalyticsEngineDataset;  // Workers Analytics Engine binding
}

function logBlock(ae: AnalyticsEngineDataset, ip: string, path: string): void {
  ae.writeDataPoint({
    blobs: [ip, path],
    doubles: [1],
    indexes: ['ip-block'],
  });
}
```

Query blocked IPs in the last hour:
```sql
SELECT blob1 AS ip, SUM(double1) AS hits
FROM <dataset>
WHERE timestamp > now() - INTERVAL '1' HOUR
AND index1 = 'ip-block'
GROUP BY ip ORDER BY hits DESC LIMIT 20
```

---

## Anti-patterns

- **Reading KV on every request with no caching**: KV is fast but not free; a high-traffic endpoint will exhaust KV read budgets and add latency.
- **Using `X-Forwarded-For` for enforcement**: can be spoofed by callers; `CF-Connecting-IP` is authoritative on Cloudflare.
- **Fail-open on KV error** (returning 200 when the list is unavailable): a misconfiguration or KV outage would bypass the control; fail-closed with 503.
- **Storing one key per IP**: an allowlist of 500 addresses becomes 500 KV reads; one JSON blob is a single read.
- **No audit log for list changes**: store a `updatedAt` and `updatedBy` field in the JSON so you know when and why the list changed.

## Gotchas

- IPv6 requires a BigInt-based range matcher; the `ipToInt` helper above handles IPv4 only. If your callers can be IPv6, add a second code path or use a library such as `ip-range-check`.
- KV consistency is eventual — a newly added IP may take up to 60 seconds to be visible globally. If a newly onboarded IP needs immediate access, instruct them to wait 90 seconds.
- `CF-Connecting-IP` is available only when the request arrives through Cloudflare's proxy. Requests from Workers Service Bindings carry an internal IP — allowlist enforcement at the inner Worker level may need a different mechanism (use Service Binding auth instead).

## Verification

```bash
# Test a blocked IP
curl -s -o /dev/null -w "%{http_code}" \
  -H "CF-Connecting-IP: 10.0.0.1" https://your-worker.example.com/admin/health
# Expected: 403

# Test an allowed IP (replace with an actual allowlisted address)
curl -s -o /dev/null -w "%{http_code}" \
  -H "CF-Connecting-IP: 203.0.113.10" https://your-worker.example.com/admin/health
# Expected: 200
```

Note: `CF-Connecting-IP` cannot be overridden by clients through Cloudflare — the header
injection above works only in local `wrangler dev` for testing.

## Related

- `workers-cors-allowlist-kv-management.md`
- `workers-ip-reputation-d1-blocklist-realtime.md`
- `workers-geofencing-geo-restriction-compliance.md`
- `x-forwarded-for-client-ip-spoofing.md`
- `kv-namespace-enumeration-prevention.md`
- `rate-limiting-per-user-d1-durable-objects.md`

## Sources

- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- CF-Connecting-IP header — https://developers.cloudflare.com/fundamentals/reference/http-request-headers/#cf-connecting-ip
- CIDR notation — RFC 4632 — https://datatracker.ietf.org/doc/html/rfc4632
