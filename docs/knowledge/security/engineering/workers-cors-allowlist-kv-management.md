# Workers CORS Allowlist Management via KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A multi-tenant Workers API must allow different origins per tenant. Hardcoding origins at
deploy time means every customer addition requires a code push. The allowed set also needs
to be revocable immediately (compromised partner domain) without a deployment.

## Context

Cloudflare Workers handle CORS entirely in application code — there is no platform-managed
allowlist. KV is the natural backing store: global replication, sub-millisecond reads from
cache, and TTL-based expiry. The challenge is doing origin validation safely (no regex
footguns) while keeping KV reads off the hot path via in-memory caching per isolate.

---

## KV Namespace Layout

Store one JSON document per logical tenant. Key pattern: `cors:tenant:<tenantId>`.

```json
{
  "origins": [
    "https://app.example.com",
    "https://staging.example.com"
  ],
  "updatedAt": "2026-08-23T00:00:00Z"
}
```

A global fallback key `cors:global` holds origins shared across all tenants.

Bind the namespace in `wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "CORS_KV"
id     = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

---

## In-Memory Cache Layer

KV reads inside Workers are fast but still add ~1–5 ms per cold read. Cache the parsed
allowlist in module-scope memory so subsequent requests in the same isolate skip KV.

```typescript
interface AllowlistEntry {
  origins: Set<string>;
  fetchedAt: number;
}

// Module-scope cache — persists across requests within one isolate lifetime.
const cache = new Map<string, AllowlistEntry>();
const CACHE_TTL_MS = 30_000; // 30 s

async function getAllowedOrigins(
  kv: KVNamespace,
  tenantId: string,
): Promise<Set<string>> {
  const now = Date.now();
  const cached = cache.get(tenantId);

  if (cached && now - cached.fetchedAt < CACHE_TTL_MS) {
    return cached.origins;
  }

  const [tenantRaw, globalRaw] = await Promise.all([
    kv.get(`cors:tenant:${tenantId}`, "json") as Promise<{ origins: string[] } | null>,
    kv.get("cors:global", "json") as Promise<{ origins: string[] } | null>,
  ]);

  const origins = new Set<string>([
    ...(tenantRaw?.origins ?? []),
    ...(globalRaw?.origins ?? []),
  ]);

  cache.set(tenantId, { origins, fetchedAt: now });
  return origins;
}
```

---

## Origin Validation

Never use a regex to match origins — anchoring mistakes silently widen the allowlist.
Use exact `Set` membership after normalising the URL.

```typescript
function normaliseOrigin(raw: string): string | null {
  try {
    const u = new URL(raw);
    // Strip path, query, fragment; keep scheme + host + explicit port.
    return u.origin; // e.g. "https://app.example.com"
  } catch {
    return null;
  }
}

function isOriginAllowed(requestOrigin: string, allowed: Set<string>): boolean {
  const normalised = normaliseOrigin(requestOrigin);
  if (!normalised) return false;
  // Reject non-HTTPS origins unless explicitly listed (http localhost permitted).
  if (!normalised.startsWith("https://") && !allowed.has(normalised)) return false;
  return allowed.has(normalised);
}
```

---

## Request Handler

```typescript
interface Env {
  CORS_KV: KVNamespace;
}

const CORS_HEADERS_BASE = {
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Tenant-ID",
  "Access-Control-Max-Age": "86400",
  // Do NOT include Access-Control-Allow-Credentials here — set per-request below.
} as const;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const requestOrigin = request.headers.get("Origin") ?? "";
    const tenantId     = request.headers.get("X-Tenant-ID") ?? "default";

    const allowed = await getAllowedOrigins(env.CORS_KV, tenantId);
    const originOk = requestOrigin !== "" && isOriginAllowed(requestOrigin, allowed);

    // Handle preflight.
    if (request.method === "OPTIONS") {
      if (!originOk) {
        return new Response(null, { status: 403 });
      }
      return new Response(null, {
        status: 204,
        headers: {
          ...CORS_HEADERS_BASE,
          "Access-Control-Allow-Origin": requestOrigin,
          "Access-Control-Allow-Credentials": "true",
          "Vary": "Origin",
        },
      });
    }

    // Process actual request.
    const response = await handleRequest(request, env);

    // Clone and attach CORS headers.
    const corsHeaders: Record<string, string> = { "Vary": "Origin" };
    if (originOk) {
      corsHeaders["Access-Control-Allow-Origin"]      = requestOrigin;
      corsHeaders["Access-Control-Allow-Credentials"] = "true";
      corsHeaders["Access-Control-Expose-Headers"]    = "X-Request-ID";
    }

    return new Response(response.body, {
      status:  response.status,
      headers: { ...Object.fromEntries(response.headers), ...corsHeaders },
    });
  },
};
```

---

## Admin API for Allowlist Updates

```typescript
async function updateTenantOrigins(
  kv: KVNamespace,
  tenantId: string,
  origins: string[],
): Promise<void> {
  // Validate every origin before writing.
  const validated = origins.map((o) => {
    const n = normaliseOrigin(o);
    if (!n) throw new Error(`Invalid origin: ${o}`);
    return n;
  });

  await kv.put(
    `cors:tenant:${tenantId}`,
    JSON.stringify({ origins: validated, updatedAt: new Date().toISOString() }),
    { expirationTtl: 60 * 60 * 24 * 365 }, // 1 year — explicit, not permanent
  );

  // Evict local isolate cache so next request re-reads.
  cache.delete(tenantId);
}
```

---

## Anti-patterns

- **Regex matching on Origin** — `origin.match(/example\.com/)` matches
  `evil-example.com`. Use exact `Set` membership only.
- **`Access-Control-Allow-Origin: *` with credentials** — browsers reject this; and
  wildcarding while also setting `Allow-Credentials: true` is a logic error that leaks
  session tokens.
- **Reflecting `Origin` without validation** — unconditionally echoing the request
  `Origin` header bypasses the entire allowlist.
- **Skipping `Vary: Origin`** — CDNs will cache a response with one origin and serve it
  to a different origin, effectively granting cross-origin access.
- **Infinite KV cache TTL** — a compromised origin can't be revoked until the isolate
  recycles. Keep TTL ≤ 60 s for security-sensitive scenarios.

## Gotchas

- KV is eventually consistent during writes — after `kv.put()` a different PoP may still
  serve the old value for up to 60 s. Force a cache bust on the admin path, but don't
  assume instant propagation globally.
- `new URL(origin).origin` returns `"null"` for opaque origins (e.g. `file://` or
  sandboxed iframes). The `normaliseOrigin` guard above rejects them via the
  `startsWith("https://")` check.
- Module-scope cache is per-isolate, not per-request. A Worker with high traffic runs
  many isolates; each has its own 30 s window. Total lag after a KV write is up to
  `CACHE_TTL_MS + KV_propagation` (≤ 90 s worst case).

## Verification

```bash
# Preflight from allowed origin → 204
curl -si -X OPTIONS https://api.example.com/v1/resource \
  -H "Origin: https://app.example.com" \
  -H "X-Tenant-ID: acme" \
  -H "Access-Control-Request-Method: POST" \
  | grep -E "HTTP|Access-Control"

# Preflight from unknown origin → 403
curl -si -X OPTIONS https://api.example.com/v1/resource \
  -H "Origin: https://evil.com" \
  -H "X-Tenant-ID: acme" \
  -H "Access-Control-Request-Method: POST" \
  | grep -E "HTTP|Access-Control"

# Verify Vary header is present on GET
curl -si https://api.example.com/v1/resource \
  -H "Origin: https://app.example.com" \
  -H "X-Tenant-ID: acme" \
  | grep -i vary
```

## Related

- `cors-cloudflare-workers-mobile-preflight.md` — mobile SDK CORS preflight quirks
- `cors-security-misconfiguration.md` — common CORS misconfigurations
- `kv-namespace-enumeration-prevention.md` — KV key design to prevent enumeration
- `multi-tenancy-isolation-workers-kv-d1.md` — tenant isolation patterns

## Sources

- Fetch Living Standard — CORS protocol: https://fetch.spec.whatwg.org/#http-cors-protocol
- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- OWASP CORS cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
