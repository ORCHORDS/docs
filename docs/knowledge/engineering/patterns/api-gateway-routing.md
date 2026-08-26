# api-gateway-routing

**Issue:** Route API requests to the right backend service
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 5 microservices. You have one CF Worker. The Worker
has 1000 lines of if/else to route to the right service. It's
hard to maintain. You add a 6th service. You forget to add it
to the router. Half your API is broken.

## Root cause
**Hard-coded routing doesn't scale.** A config-driven or
file-based routing is more maintainable.

**Source:** Various gateway design guides.

## The patterns

### 1. Path-based routing
```ts
// In a CF Pages Function
const routes: Record<string, (req: Request, env: Env) => Promise<Response>> = {
  '/api/users': handleUsers,
  '/api/posts': handlePosts,
  '/api/comments': handleComments,
};

export const onRequest: PagesFunction = async (context) => {
  const url = new URL(context.request.url);
  const route = routes[url.pathname];
  if (!route) return new Response('Not found', { status: 404 });
  return route(context.request, context.env);
};
```

✅ Simple
❌ Hard-coded; adding a service requires code change

### 2. Service bindings
```ts
// In wrangler.toml
[[services]]
binding = "USERS_SERVICE"
service = "users-service"

[[services]]
binding = "POSTS_SERVICE"
service = "posts-service"

// In the router
const routes: Record<string, Fetcher> = {
  '/api/users': env.USERS_SERVICE,
  '/api/posts': env.POSTS_SERVICE,
};
```

✅ Native CF feature, no HTTP overhead
❌ Still hard-coded

### 3. File-based routing (Cloudflare Pages Functions)
CF Pages Functions has built-in file-based routing:
- `functions/api/users/[[path]].ts` matches `/api/users/*`
- `functions/api/posts/[[path]].ts` matches `/api/posts/*`

The path IS the routing config. No code needed.

✅ Auto-discovered, no config
❌ Less flexible (can't have dynamic routing)

### 4. Traefik / Kong / External gateway
For a non-CF backend:
```yaml
# Traefik dynamic config
http:
  routers:
    users-router:
      rule: "PathPrefix(`/api/users`)"
      service: users-service
    posts-router:
      rule: "PathPrefix(`/api/posts`)"
      service: posts-service
  services:
    users-service:
      loadBalancer:
        servers:
          - url: http://users-service.internal
```

✅ Battle-tested, dynamic config
❌ Another service to operate

### 5. Service mesh (Istio, Linkerd)
For Kubernetes-based deployments, a service mesh handles
routing + observability:
```yaml
# Istio VirtualService
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: users-service
spec:
  hosts:
    - users-service
  http:
    - match:
        - uri:
            prefix: /api/users
      route:
        - destination:
            host: users-service
            port:
              number: 80
```

✅ Sophisticated (retries, circuit breaking, observability)
❌ Complex; only for K8s

## The decision matrix

| Service count | Team size | Use |
|---|---|---|
| 1 | Any | Single Worker, no router needed |
| 2-5 | Small | File-based or path-based |
| 5-10 | Medium | Service bindings (CF) or Traefik |
| 10+ | Large | Service mesh (K8s) or Kong/Apigee |

## The "path vs host" choice

### Path-based (e.g. `/api/users/*`)
- ✅ One domain, multiple services
- ✅ Easier to manage (DNS + TLS)
- ❌ All services share the same wildcard TLS cert

### Host-based (e.g. `users.api.example.com`)
- ✅ Different certs per service
- ✅ Different origins (no shared CORS, no shared cookies)
- ❌ More DNS to manage
- ❌ More TLS certs to renew

For most apps, path-based is simpler. Use host-based if you
need stricter isolation.

## The "header-based" pattern

For internal services, route by header:
```
POST / HTTP/1.1
Host: gateway.example.com
X-Service: users
```

The gateway reads the `X-Service` header and routes. This is
used by service meshes (Envoy) but not by humans (browsers
can't set custom headers).

## Verification
- **Test:** `test/routing.test.ts > each path routes to the
  right service` — passes
- **Test:** `test/routing.test.ts > unknown path returns 404` —
  passes
- **Live:** The gateway log shows every request + which
  service handled it

## Gotchas
- **The order of routes matters.** If `/api/users` is a
  catch-all but `/api/users/me` is a specific route, the
  specific must come first.
- **Routing rules can have side effects.** A rule that
  rewrites a URL can break the client's assumptions. Test
  the rewrite end-to-end.
- **A gateway is a SPOF.** If the gateway is down, all APIs
  are down. Have multi-region + monitoring.
- **A gateway can leak tenant data.** If the routing is based
  on tenant_id in the URL, and the tenant_id is user-controlled,
  the user can route to other tenants' services. Use
  server-derived tenant_id.
- **Some routing changes require cache invalidation.** If
  the gateway caches routing decisions, a route change doesn't
  take effect until the cache expires.

## Related
- `api-gateway-pattern.md`
- `pages-functions-exact-match-routing.md`
- `cors-pages-functions.md` (CORS at the gateway)
- `multi-tenant-data-isolation.md` (tenant-scoped routing)
