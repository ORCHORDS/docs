# Workers Response Cache-Control for Sensitive Data

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An authenticated API endpoint returns user-specific JSON. A security scan or incident
reveals that Cloudflare's edge cache — or a downstream corporate proxy / shared browser
cache — served one user's data to a different user. The root cause is missing or incorrect
`Cache-Control` headers on responses that should never be stored.

## Context

Cloudflare Workers run in front of the CDN cache. By default, Workers responses are not
cached by Cloudflare's edge unless you explicitly call `cache.put()` or set `cf.cacheTtl`.
However, downstream proxies, mobile operating systems, and browsers apply their own caching
rules based solely on the `Cache-Control` and `Expires` headers your Worker sends. If those
headers are absent or permissive, user-specific responses can persist in shared caches.
Correctly setting `Cache-Control` is a defence-in-depth requirement even when you trust
Cloudflare's cache behaviour.

---

## The Four Directives That Matter for Security

| Directive       | Meaning                                                                 |
|-----------------|-------------------------------------------------------------------------|
| `no-store`      | Do not write the response to any cache storage, ever.                   |
| `no-cache`      | Store the response, but revalidate with the origin before reuse.        |
| `private`       | Only the end-user's browser cache may store this; no shared caches.     |
| `must-revalidate` | Once stale, the cached copy cannot be used without revalidation.      |

For authenticated endpoints: use `no-store`. Do not use `no-cache` or `private` alone —
they permit storage and only control revalidation / sharing semantics.

---

## Utility: Building Cache-Control for Common Cases

```typescript
type CacheProfile =
  | "no-store"          // Authenticated, personalised — never cache
  | "private-revalidate" // Browser-only cache, revalidate each time
  | "public-short"      // Public data, short edge cache (1 min)
  | "public-long"       // Immutable public assets (1 year)
  | "no-cache-public";  // Shared cache allowed but must revalidate

const CACHE_PROFILES: Record<CacheProfile, string> = {
  "no-store":          "no-store",
  "private-revalidate": "private, no-cache, must-revalidate",
  "public-short":      "public, max-age=60, s-maxage=60, stale-while-revalidate=30",
  "public-long":       "public, max-age=31536000, immutable",
  "no-cache-public":   "public, no-cache, must-revalidate",
};

function addCacheHeaders(
  headers: Headers,
  profile: CacheProfile,
): void {
  headers.set("Cache-Control", CACHE_PROFILES[profile]);

  if (profile === "no-store" || profile.startsWith("private")) {
    // Belt-and-suspenders: Pragma is obsolete but still respected by old proxies.
    headers.set("Pragma", "no-cache");
    // Remove any Expires that might encourage caching.
    headers.delete("Expires");
    // Vary: Authorization prevents shared-cache poisoning even if no-store is ignored.
    headers.set("Vary", "Authorization");
  }
}
```

---

## Middleware: Automatic Classification by Route

```typescript
interface RoutePolicy {
  pattern: RegExp;
  profile: CacheProfile;
}

const ROUTE_POLICIES: RoutePolicy[] = [
  // Authenticated API routes — never cache.
  { pattern: /^\/api\/v\d+\//,       profile: "no-store" },
  // Admin routes — never cache.
  { pattern: /^\/admin\//,           profile: "no-store" },
  // Public API endpoints — short edge cache.
  { pattern: /^\/api\/public\//,     profile: "public-short" },
  // Static fingerprinted assets — long immutable cache.
  { pattern: /^\/assets\/[^/]+\.\w{8,}\.(js|css|woff2|png|webp)$/, profile: "public-long" },
];

function classifyRoute(pathname: string): CacheProfile {
  for (const { pattern, profile } of ROUTE_POLICIES) {
    if (pattern.test(pathname)) return profile;
  }
  return "no-store"; // Safe default: unknown routes get no-store.
}

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const response = await handleRequest(request);

    const profile = classifyRoute(url.pathname);
    const headers = new Headers(response.headers);

    addCacheHeaders(headers, profile);

    // Prevent Cloudflare's edge cache from storing authenticated responses
    // even when using cf.cacheTtl elsewhere in the codebase.
    if (profile === "no-store") {
      headers.set("CDN-Cache-Control", "no-store");
      headers.set("Surrogate-Control", "no-store");
    }

    return new Response(response.body, {
      status:  response.status,
      headers,
    });
  },
};
```

---

## Vary Header Management

`Vary` tells caches which request headers must match for a cached response to be reused.
Incorrect `Vary` usage causes either under-sharing (performance loss) or over-sharing
(security bug).

```typescript
function setVaryHeaders(headers: Headers, profile: CacheProfile): void {
  switch (profile) {
    case "no-store":
      // no-store responses should not be cached at all; still set Vary defensively.
      headers.set("Vary", "Authorization, Cookie");
      break;
    case "public-short":
      // Public content may vary by Accept-Encoding and Accept-Language.
      headers.set("Vary", "Accept-Encoding, Accept-Language");
      break;
    case "public-long":
      // Fingerprinted assets do not vary — omit Vary for maximum cache efficiency.
      headers.delete("Vary");
      break;
    default:
      headers.set("Vary", "Authorization");
  }
}
```

---

## Detecting Cached Sensitive Responses in Tests

```typescript
// Integration test helper — run in Vitest or Jest with miniflare.
async function assertNotCached(
  fetch: typeof globalThis.fetch,
  url: string,
  authToken: string,
): Promise<void> {
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${authToken}` },
  });

  const cc = res.headers.get("Cache-Control") ?? "";
  const pragma = res.headers.get("Pragma") ?? "";

  if (!cc.includes("no-store")) {
    throw new Error(
      `Authenticated endpoint ${url} missing no-store. Cache-Control: "${cc}"`,
    );
  }

  // CF-Cache-Status should be MISS or DYNAMIC for no-store responses.
  const cfStatus = res.headers.get("CF-Cache-Status");
  if (cfStatus && !["MISS", "DYNAMIC", "BYPASS", "EXPIRED"].includes(cfStatus)) {
    throw new Error(
      `Authenticated endpoint ${url} served from cache! CF-Cache-Status: ${cfStatus}`,
    );
  }
}
```

---

## Handling ETags and Conditional Requests on Authenticated Endpoints

Some authenticated endpoints legitimately want conditional request support (`If-None-Match`
→ 304) for bandwidth savings. The cache control headers and security properties are
compatible when done correctly:

```typescript
function buildAuthenticatedResponse(
  body: string,
  etag: string,
  request: Request,
): Response {
  const ifNoneMatch = request.headers.get("If-None-Match");

  if (ifNoneMatch === etag) {
    // Return 304 without body — still include security cache headers.
    return new Response(null, {
      status: 304,
      headers: {
        "ETag":          etag,
        "Cache-Control": "no-store",
        "Vary":          "Authorization",
      },
    });
  }

  return new Response(body, {
    headers: {
      "Content-Type":  "application/json",
      "ETag":          etag,
      "Cache-Control": "no-store",
      "Vary":          "Authorization",
    },
  });
}
```

---

## Anti-patterns

- **`Cache-Control: private` alone** — permits browser-local storage; a shared device
  (library kiosk, corporate terminal) will serve user A's data to user B.
- **`Cache-Control: no-cache` alone** — the response IS stored; it just requires
  revalidation. If the origin is unreachable, stale data may be served.
- **Omitting `Cache-Control` on authenticated responses** — browsers and proxies apply
  heuristic caching rules (often caching responses with `200 OK` and no explicit
  directive for a percentage of the `Last-Modified` age).
- **`Vary: *`** — semantically correct (prevents all caching) but many proxies treat it
  as uncacheable without forwarding it; causes performance collapse with no security
  benefit over `no-store`.
- **Caching `Set-Cookie` responses** — if a response both sets a cookie and is cached, a
  second user can receive a stale `Set-Cookie` from a previous session.

## Gotchas

- `CF-Cache-Status: DYNAMIC` is Cloudflare's indicator that a response was not eligible
  for caching (often due to `no-store`). This header is reliable only at Cloudflare's
  edge; downstream proxies have no equivalent.
- `CDN-Cache-Control` and `Surrogate-Control` are Cloudflare-specific headers that
  override `Cache-Control` for the edge cache only, without affecting browser behaviour.
- Cloudflare strips `Set-Cookie` before caching a response — if your Worker sets cookies,
  the response is automatically bypassed at the edge (CF-Cache-Status: BYPASS). You still
  need `no-store` for downstream proxies.
- Browsers sometimes ignore `no-store` on navigation responses in bfcache (back-forward
  cache). Add `Cache-Control: no-store` plus the `Clear-Site-Data` header on logout to
  purge bfcache for auth-critical flows.

## Verification

```bash
# Authenticated endpoint must have no-store and not be served from CF cache.
curl -si https://api.example.com/v1/profile \
  -H "Authorization: Bearer $TOKEN" \
  | grep -iE "cache-control|cf-cache-status|pragma"

# Public endpoint should show CF-Cache-Status: HIT on second request.
curl -si https://api.example.com/api/public/status && \
curl -si https://api.example.com/api/public/status \
  | grep -i cf-cache-status

# Verify no-store is present in response from a fresh fetch (no cached copy).
npx wrangler dev --local &
curl -si http://localhost:8787/api/v1/me \
  -H "Authorization: Bearer test-token" \
  | grep -i cache-control
```

## Related

- `web-cache-deception-path-confusion.md` — cache deception via path suffix abuse
- `web-cache-poisoning-unkeyed-inputs.md` — cache poisoning via unkeyed request inputs
- `workers-error-response-information-disclosure.md` — safe error body handling
- `cloudflare-pages-headers-security-file.md` — applying cache headers via _headers file

## Sources

- RFC 9111 — HTTP Caching: https://www.rfc-editor.org/rfc/rfc9111
- Cloudflare CDN-Cache-Control: https://developers.cloudflare.com/cache/concepts/cdn-cache-control/
- MDN Cache-Control: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
- OWASP Caching Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#web-content-caching
