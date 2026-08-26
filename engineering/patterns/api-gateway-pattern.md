# api-gateway-pattern

**Issue:** API gateway — when you need one, what to use
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 5 microservices. Each has its own auth, rate limit,
CORS, logging. You add a new service. You copy the auth + rate
limit + CORS code. Now you have 6 copies. A bug in one is a
bug in 5. You wish you had a central place for cross-cutting
concerns.

## Root cause
**Cross-cutting concerns (auth, rate limit, CORS, logging) are
duplicated across services.** A central gateway handles them
once.

**Source:** Microsoft — API Gateway pattern:
https://learn.microsoft.com/en-us/azure/architecture/microservices/design/gateway

> "A gateway is a single entry point for all clients. It
> handles cross-cutting concerns and routes requests to
> appropriate backend services."

## The 3 main options

### 1. CF Workers as a gateway
For a CF-native stack, use a Workers-based gateway:
```ts
// Gateway worker
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // 1. Auth (centralized)
    const user = await authenticate(request, env);
    if (!user) return new Response('Unauthorized', { status: 401 });

    // 2. Rate limit (centralized)
    const rateLimited = await checkRateLimit(user, env);
    if (rateLimited) return rateLimited;

    // 3. CORS (centralized)
    const corsHeaders = buildCorsHeaders(request);

    // 4. Route to backend
    let response: Response;
    if (url.pathname.startsWith('/api/users')) {
      response = await env.USERS_SERVICE.fetch(request);
    } else if (url.pathname.startsWith('/api/posts')) {
      response = await env.POSTS_SERVICE.fetch(request);
    } else {
      return new Response('Not found', { status: 404 });
    }

    // 5. Logging (centralized)
    console.log({
      level: 'info',
      message: 'request',
      path: url.pathname,
      userId: user.id,
      status: response.status,
      durationMs: Date.now() - ctx.startTime,
    });

    // 6. Add CORS headers
    for (const [k, v] of corsHeaders.entries()) {
      response.headers.set(k, v);
    }
    return response;
  },
};
```

✅ Single entry point
✅ Cross-cutting concerns centralized
✅ Easy to add a new service
❌ Latency: extra hop (Worker → service)
❌ Single point of failure (if gateway is down, all APIs are down)

### 2. Service bindings (CF native)
Instead of HTTP routing, use service bindings:
```ts
// In wrangler.toml
[[services]]
binding = "USERS_SERVICE"
service = "users-service"

[[services]]
binding = "POSTS_SERVICE"
service = "posts-service"
```

```ts
// In the gateway
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/users')) {
      return env.USERS_SERVICE.fetch(request);  // No HTTP; direct RPC
    }
    // ...
  },
};
```

✅ No HTTP overhead (direct RPC between isolates)
✅ Same cross-cutting concerns as the HTTP gateway
✅ Native CF feature

### 3. External gateway (Kong, AWS API Gateway, Tyk)
For a non-CF backend, use an external gateway:
```yaml
# Kong config
services:
  - name: users
    url: https://users-service.internal
    routes:
      - paths: ["/api/users"]
    plugins:
      - name: key-auth
        config:
          key_names: ["X-API-Key"]
      - name: rate-limiting
        config:
          minute: 100
```

✅ Battle-tested
✅ Rich plugin ecosystem
❌ Operational overhead
❌ Another vendor

## When to use a gateway

✅ Use a gateway when:
- **You have 3+ services** with cross-cutting concerns
- **The cross-cutting concerns are duplicated** (auth in 5
  places)
- **You need central rate limiting / observability**
- **You want to expose a unified API to clients**

❌ Don't use a gateway when:
- **You have 1-2 services** (YAGNI)
- **The latency overhead is unacceptable** (every request
  adds 5-10ms)
- **You can solve it with shared libraries** (if all services
  are in the same language)

## Cross-cutting concerns in a gateway

### Auth
- Verify the session token
- Check scopes / permissions
- Pass the user identity to the backend (via header or
  service binding)

### Rate limit
- Per-user, per-tenant, per-IP
- Configurable per-endpoint

### CORS
- Set CORS headers once
- Handle preflight (OPTIONS)

### Logging
- Log every request (with user, path, status, latency)
- Include trace ID for correlation

### Transformation
- Add / remove headers
- Rewrite paths
- Aggregate responses from multiple services

### Auth + service discovery
For a CF Workers setup, the gateway can ALSO be the service
discovery:
```ts
// Per-tenant service routing
if (url.pathname.startsWith('/api/users')) {
  // Route to the user's tenant's instance
  return env.TENANT_ROUTER.fetch(request, { headers: { 'X-Tenant-Id': user.tenantId } });
}
```

## Verification
- **Test:** `test/gateway.test.ts > request is authenticated,
  rate-limited, logged, and routed` — passes
- **Live:** The gateway is the single entry point (verified
  via CF logs)
- **Audit:** Quarterly review of gateway config

## Gotchas
- **A gateway is a SPOF.** If the gateway is down, all APIs
  are down. Have a multi-region deployment + monitoring.
- **The gateway can become a monolith.** It grows over time
  (auth + rate limit + CORS + logging + transformation +
  caching + ...). Keep it focused.
- **Auth at the gateway is a defense layer, not the only
  one.** Each backend should ALSO verify auth (defense in
  depth). The gateway might be bypassed (direct service
  access, debugging, etc.).
- **Service bindings don't have HTTP overhead but DO have RPC
  overhead.** For tight latency budgets, profile.
- **The gateway's auth + the backend's auth must be the same.**
  If the gateway uses session cookies but the backend uses
  API keys, the two can drift.

## Related
- `cors-pages-functions.md` (the CORS concern)
- `rate-limiting-strategies.md` (the rate limit concern)
- `session-cookies-vs-jwt.md` (the auth concern)
- CF service bindings: https://developers.cloudflare.com/workers/configuration/bindings/#service-bindings
- Microsoft: https://learn.microsoft.com/en-us/azure/architecture/microservices/design/gateway
