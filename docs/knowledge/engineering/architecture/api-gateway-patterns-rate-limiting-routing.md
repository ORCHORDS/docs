# API Gateway Patterns — Rate Limiting, Authentication, and Request Routing

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your microservices architecture has 12 backend services. Each service
implements its own JWT validation, rate limiting, and CORS handling.
A security audit reveals three services accept expired tokens, two
services have no rate limiting, and one service returns stack traces
to clients. Authentication logic is copy-pasted across repositories
with subtle differences in each copy. When you need to rotate the
JWT signing key, you must update and redeploy all 12 services.

## Context

An API gateway centralizes cross-cutting concerns — authentication,
rate limiting, request routing, circuit breaking, and observability —
at a single ingress point. In 2026, the primary options are Kong
(Lua/NGINX, largest plugin ecosystem), Envoy (C++, highest throughput,
service mesh data plane), Traefik (Go, Docker/Kubernetes auto-
discovery), and AWS API Gateway (serverless, AWS-native). The gateway
handles authentication (who are you); backend services handle
authorization (what can you do). Keep business logic out of the
gateway — it should contain only cross-cutting concerns.

## Gateway comparison (2026)

```
                Kong          Envoy         Traefik       AWS API GW
────────────────────────────────────────────────────────────────────
Throughput:     ~25K RPS      ~50K+ RPS     ~20K RPS      Managed
Latency:        ~2ms          <1ms          ~2ms          Variable
Memory:         ~80MB         ~30MB         ~50MB         N/A
Language:       Lua/NGINX     C++           Go            Managed
Plugins:        200+ (Hub)    WASM filters  ~30 built-in  AWS integrations
mTLS:           Plugin        Native        Built-in      ACM
Best for:       API mgmt      Service mesh  Docker/K8s    Serverless
```

## Rate limiting patterns

```
Four algorithms:

Token Bucket:     Burst-friendly, most common
                  Allows bursts up to bucket size, refills at fixed rate
Sliding Window:   Smooth limiting, no boundary spikes
                  More complex, higher memory (sorted set per key)
Fixed Window:     Simple deployments
                  Boundary spike problem (2x burst at window edges)
Leaky Bucket:     Consistent output rate
                  Queuing delay, smooths bursty traffic

Typical tier limits:
  Unauthenticated:  60 req/hour (by IP)
  Free:             100 req/min
  Pro:              1,000 req/min
  Enterprise:       10,000 req/min + custom

Redis-backed implementation:
  Key: rate_limit:{user_id}:{window}
  Fixed window: INCR + EXPIRE
  Sliding window: Sorted set with timestamp scores
```

```yaml
# Kong rate-limiting plugin
plugins:
  - name: rate-limiting
    config:
      minute: 100
      policy: redis
      redis_host: redis.internal
      redis_port: 6379

# Traefik rate-limit middleware
http:
  middlewares:
    ratelimit:
      rateLimit:
        average: 100
        burst: 50
```

## JWT validation at the gateway

```
Authentication flow:

  Client → Gateway → Verify JWT signature + claims
                   → Extract user_id, roles
                   → Forward X-User-ID, X-Roles headers
                   → Backend trusts gateway headers

Token lifecycle:
  Access tokens:  5-15 minutes (short-lived)
  Refresh tokens: Long-lived (client-managed)

Validation approaches (ranked by common use):
  1. JWT signature verification + claims extraction
  2. OAuth2 token introspection (real-time revocation, higher latency)
  3. API key lookup in Redis/database
  4. Mutual TLS for service-to-service

Claims to validate:
  exp:  Token expiration
  iat:  Issued-at time
  iss:  Expected issuer
  aud:  Expected audience
```

## Circuit breaker integration

```
State machine:

  CLOSED (normal) → 50% failure rate in 10 requests → OPEN
  OPEN → return 503 for 60 seconds → HALF-OPEN
  HALF-OPEN → test single request:
    200 OK  → CLOSED (resume normal)
    5xx     → OPEN (restart wait)

Envoy: "Outlier detection" ejects unhealthy instances after
consecutive 5xx errors. Built-in, no plugin needed.

Kong: circuit-breaker plugin with threshold-based tripping.

Best practice: combine circuit breakers with active health checks.
Poll /healthz on backends to trip pre-emptively before user
requests fail.
```

## Request transformation and canary routing

```
Common transformations:
  → Header injection: X-Request-ID, X-User-ID from JWT
  → Body conversion: XML ↔ JSON for legacy backends
  → Response filtering: strip internal fields before client delivery
  → Protocol translation: HTTP/REST to gRPC internally

Canary routing:
  Start at 5% traffic → 25% → 50% → 100%
  Monitor error rates and latency at each step

  Envoy: native weighted clusters in route configuration
  Traefik: weighted round-robin via service weights
  Kong: canary-release plugin with percentage-based splitting
```

## Observability integration

```yaml
# Kong OpenTelemetry plugin (bundled since Kong 3.0)
plugins:
  - name: opentelemetry
    config:
      traces_endpoint: http://otel-collector:4318/v1/traces
      resource_attributes:
        service.name: kong-gateway
        deployment.environment: production
      sampling_rate: 1.0
      propagation:
        default_format: w3c
```

```
Key metrics to track at the gateway:
  → Requests/sec per upstream service
  → p50/p95/p99 latency breakdown
  → Error rate by upstream and status code
  → Active connections
  → Rate limit hits (count and percentage)
  → Circuit breaker state transitions

Cache hit latency: ~1ms vs cache miss + backend: ~50ms
Use W3C Trace Context (traceparent/tracestate) across all services
```

## Anti-patterns

- **"God Gateway"** — putting business logic in the gateway. Keep it
  to cross-cutting concerns only (auth, rate limiting, routing,
  observability). Business rules belong in services.
- **Single point of failure** — deploy gateway clusters behind load
  balancers, minimum 3 instances. A single gateway instance takes
  down everything.
- **Static backend configuration** — use service discovery (Consul,
  Kubernetes DNS) instead of hardcoded upstream addresses. Static
  config breaks when backends scale or move.
- **No response caching** — gateway-level caching reduces backend
  load dramatically. Cache hit at ~1ms vs backend roundtrip at ~50ms.

## Gotchas

- **Rate limiting across multiple gateway instances** — local counters
  allow N × limit when running N instances. Use Redis or a shared
  store for distributed rate limiting.
- **JWT clock skew** — allow 30-60 seconds of clock skew tolerance
  when validating `exp` and `iat` claims. Servers are rarely
  perfectly synchronized.
- **Health check false positives** — a `/healthz` endpoint that
  returns 200 without checking dependencies (database, cache) masks
  real failures. Health checks should verify critical dependencies.
- **Gateway timeout vs backend timeout** — set gateway timeout
  slightly longer than the backend's timeout. If the gateway times
  out first, it drops the connection while the backend continues
  processing, wasting resources.
- **429 without Retry-After** — always include a `Retry-After` header
  with 429 responses. Clients without it retry immediately, making
  overload worse.

## Verification

- Gateway handles auth, rate limiting, and CORS — backends do not.
- Rate limiting uses a shared store (Redis) across gateway instances.
- JWT validation checks signature, expiration, issuer, and audience.
- Circuit breakers combined with active health checks on all upstreams.
- OpenTelemetry traces propagate through the gateway to backends.
- Gateway deployed as a cluster (minimum 3 instances).

## Related

- `documentation/docs/policies/architecture/event-sourcing-projections-snapshots.md`
- `documentation/docs/policies/performance/sse-vs-websockets-real-time-streaming.md`
- `documentation/docs/policies/infra/kubernetes-network-policies-service-mesh.md`

## Source URLs (verified 2026-08-16)

- API Gateway Patterns: Kong vs Envoy vs Traefik in 2025 — https://dev.to/yash_pritwani_07a77613fd6/api-gateway-patterns-kong-vs-envoy-vs-traefik-in-2025-1d46
- API Gateway Patterns: Authentication, Rate Limiting, and Routing at Scale — https://codelit.io/blog/api-gateway-patterns-and-best-practices
- Top 10 Technical API Gateway Best Practices for 2026 — https://opsmoon.com/blog/api-gateway-best-practices/
- How to Instrument Kong API Gateway with OpenTelemetry — https://oneuptime.com/blog/post/2026-02-06-instrument-kong-api-gateway-opentelemetry/view
