# Decorator Pattern Traffic Shaping Layer

## Scope

This article covers the Decorator pattern — GoF structural pattern attaching responsibilities to an object dynamically by wrapping it in an object with the same interface — applied to traffic shaping: rate limiting, quota enforcement, admission control, request prioritization, and load smoothing layered over an existing handler without modifying it. Scope includes wrapper composition order, per-identity shaping state, the interaction between shaping layers and caching layers, and failure semantics of the wrapper stack. It excludes server-side autoscaling and queue-based load leveling upstream of the application, and excludes authorization (a validation-pipeline concern) even though decorators are also a valid vehicle for it.

## Workflow or implementation guidance

Model shaping as nested decorators over the handler interface, each wrapping the next with identical signature:

```ts
type Handler = (req: Request, ctx: Context) => Promise<Response>;

const withRateLimit = (limit: RateLimiter, next: Handler): Handler => async (req, ctx) => {
  const verdict = await limit.check(identity(req));
  if (!verdict.allowed) return tooManyRequests(verdict.retryAfter);
  return next(req, ctx);
};
```

Composition order is the design decision with real consequences, and it follows one rule: enforce in order of cheapness and certainty, outermost first. Identity resolution and rate limiting belong outside caching (why serve a cache hit to a caller who is over quota?), caching belongs outside the expensive handler, and concurrency caps belong inside or outside caching depending on whether the expensive resource is the cache's backend. Document the assembled order per route as a visible list, because a decorator stack whose order lives only in a call graph cannot be reviewed for correctness.

Give each decorator exactly one responsibility and one failure policy. A decorator that both limits and caches will evolve both incorrectly. Each decorator must declare what happens when its own dependencies fail: a rate limiter whose counter store is unreachable must choose fail-open (allow, alert) or fail-closed (reject everything) explicitly, with the choice recorded — a default chosen by accident becomes an outage or an abuse window. State must be scoped per identity class, and identity resolution must be explicit: per API key, per tenant, per IP as last resort. Anonymous IP-based shaping behind a shared egress proxy collapses to shaping everyone as one user, which is both too strict and too lax in the wrong places.

Pair limiters with meaningful rejection responses: a 429 carrying `Retry-After` and a stable internal reason code, so well-behaved clients back off correctly instead of hammering harder.

## Controls

Pin the decorator order per route in a reviewable composition table — route, ordered list of decorators, parameters — and require a diff review when it changes, since reordering silently changes rejection semantics. Require every shaping decorator to emit three metrics through one shared naming convention: allowed count, rejected count with reason, and its own dependency latency; without uniform naming, operators cannot compare limiters. Set an explicit fail-open/fail-closed policy per decorator in its configuration, not in code branches, and verify the policy with a fault-injection test that severs the decorator's dependency. Audit identity scoping: a quarterly check that every new route's shaping key is documented and that no route shapes on raw IP behind a known proxy. Bound memory in any in-process token bucket: buckets per identity with an eviction policy, because unbounded identity-keyed maps are a slow leak that presents as an outage weeks later.

## Validation evidence

Validation is behavioral under concurrency. For each shaping decorator, drive concurrent load from many identities at once and assert the enforced rate matches configuration within a tolerance — token-bucket implementations fail under concurrency in ways unit tests never reveal (lost increments, double grants). Boundary tests: at exactly the limit and one past it, assert allow then reject with correct headers. Order tests: golden fixture requests per route asserting which decorator rejects a given malformed, over-quota, or unauthenticated request, so an accidental reorder fails a named test. Failover tests: with the limiter's dependency down, assert the configured fail-open or fail-closed behavior and that the alert fires. Interaction tests: verify the cache-plus-limiter composition does not serve cached responses over quota and that cache hits do not consume expensive-handler concurrency slots. Soak evidence: a multi-hour run with ramping identity cardinality, asserting stable memory and correct aggregate throughput — this catches the identity-map leak and any clock-skew sensitivity in refill logic.

## Failure modes and correction

The most common failure is silent reordering during refactoring: someone inlines a decorator or rebuilds the stack without one layer, and rejections stop (or start) without any test noticing. Correct with the composition-table control and order-sensitive fixture tests. The second is the omniscient decorator: a "middleware" that limits, caches, rewrites headers, and catches errors, whose behavior no one can predict and whose failure modes interact. Correct by splitting along the single-responsibility rule; wrapping is cheap. A third is shared-state misplacement: in-process counters on a horizontally scaled runtime multiply the effective limit by instance count — ten instances each allowing one hundred requests per second jointly allow one thousand. Correct by centralizing the counter in a shared, atomic store, or by dividing the budget per instance with an explicit instance-count assumption. A fourth is fail-open-by-accident: an unhandled exception in the limiter is caught by a generic error handler that returns a success-shaped path, neutering the control. Correct by giving decorators their own try/catch with the declared policy. A fifth is identity collapse behind proxies: shaping by client IP when all traffic arrives from one egress treats the world as one client. Correct by resolving identity from authenticated tokens or keys first, IP only as fallback.

## Limitations

Decorators add per-request allocation and indirection; deep stacks on hot paths cost measurable latency, and diagnosing which layer rejected a request requires disciplined propagation of reason codes through the stack. The pattern shapes traffic at the application layer only — it cannot protect resources consumed before the stack runs (TLS termination, body buffering) nor enforce anything for traffic that never reaches the application. Per-identity shaping needs shared state to be correct across instances, which introduces a dependency whose availability becomes part of the request path — the very dependency whose failure forces the fail-open/fail-closed dilemma. Rate-limit semantics themselves are surprisingly subtle (fixed window bursts, sliding-window memory, token-bucket burst tolerance), and the decorator pattern neither chooses nor tunes these; misconfiguration is easy and invisible until abuse or load exposes it. Finally, wrapper stacks obscure control flow for new engineers — a request's journey through six decorators must be documented deliberately or understood only by its author.

## Canonical sources

- Gamma, Helm, Johnson, and Vlissides — Design Patterns: Elements of Reusable Object-Oriented Software, Addison-Wesley, 1994 (Decorator, Structural Patterns catalog).
- Envoy Proxy architecture overview — HTTP filters (decorator-chain traffic shaping at the infrastructure layer): https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/http/http_filters
- Cloudflare documentation — Rate limiting rules (identity-scoped traffic shaping semantics): https://developers.cloudflare.com/waf/rate-limiting-rules/
- Microsoft Azure Architecture Center — Queue-Based Load Leveling pattern (complementary shaping at the architecture layer): https://learn.microsoft.com/en-us/azure/architecture/patterns/queue-based-load-leveling
