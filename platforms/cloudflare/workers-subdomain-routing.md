# workers-subdomain-routing

**Issue:** Routing requests to different Workers or origins based on subdomain
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When you have multiple services (API, auth, admin) on different subdomains, you can either deploy separate Workers per subdomain or use a single router Worker that dispatches based on the `Host` header. Both approaches are valid.

## Pattern / Solution

**Approach 1 — Separate Workers per subdomain:**
```toml
# api-worker/wrangler.toml
[[custom_domains]]
pattern = "api.example.com"

# auth-worker/wrangler.toml
[[custom_domains]]
pattern = "auth.example.com"
```
Simple but requires separate deployments.

---

**Approach 2 — Single router Worker (monorepo):**
```typescript
// router/src/index.ts
export interface Env {
  API_SERVICE: Fetcher;       // Service Binding to api-worker
  AUTH_SERVICE: Fetcher;      // Service Binding to auth-worker
  ADMIN_SERVICE: Fetcher;     // Service Binding to admin-worker
}

const ROUTES: Record<string, keyof Env> = {
  'api.example.com': 'API_SERVICE',
  'auth.example.com': 'AUTH_SERVICE',
  'admin.example.com': 'ADMIN_SERVICE',
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const host = new URL(request.url).hostname;
    const serviceKey = ROUTES[host];

    if (!serviceKey) {
      return new Response('Not Found', { status: 404 });
    }

    const service = env[serviceKey] as Fetcher;
    return service.fetch(request);
  },
};
```

```toml
# router/wrangler.toml
[[custom_domains]]
pattern = "api.example.com"

[[custom_domains]]
pattern = "auth.example.com"

[[custom_domains]]
pattern = "admin.example.com"

[[services]]
binding = "API_SERVICE"
service = "api-worker"

[[services]]
binding = "AUTH_SERVICE"
service = "auth-worker"

[[services]]
binding = "ADMIN_SERVICE"
service = "admin-worker"
```

**Wildcard route (zone-level):**
```toml
# Matches any subdomain of example.com
[[routes]]
pattern = "*.example.com/*"
zone_name = "example.com"
```

## Gotchas
- A Custom Domain gives the Worker exclusive ownership of that hostname; Routes let the origin also handle non-matching paths.
- When using a router + Service Bindings, the original `Host` header is preserved — no need to rewrite it.
- Wildcard Custom Domains (`*.example.com`) require an Enterprise plan; wildcard Routes work on all plans.
- Do not create both a Custom Domain and a Route for the same hostname — they conflict.
- The router Worker adds ~0 ms latency when using Service Bindings (in-process call).

## Related
- `workers-custom-domains.md`
- `workers-service-bindings-advanced.md`
- `pages-redirects-config.md`
