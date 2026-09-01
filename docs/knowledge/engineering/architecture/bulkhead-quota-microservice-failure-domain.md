# Bulkhead Quota Microservice Failure Domain

## Scope

This article addresses the bulkhead pattern as it applies to microservice failure domains. It explains how to partition resources (threads, connections, queues, memory) so that a fault in one service or one tenant cannot exhaust the resources of the system as a whole. The discussion covers both client-side bulkheads (in the caller) and server-side bulkheads (in the callee), as well as the connection-pool, thread-pool, and queue-based implementations. The article applies to JVM services, Go services, Node.js services, and edge runtimes such as Cloudflare Workers, each of which has its own primitives for bulkhead isolation.

## Workflow or implementation guidance

A bulkhead is a structural mechanism that bounds the resources one consumer can consume from a shared pool. The classic ship metaphor is exact: a breach in one compartment must not flood the others. In microservices, the consumer is usually a caller that talks to several downstream services, and the shared resource is typically a connection pool, a thread pool, or a queue. Without bulkheads, a slow or failing downstream can saturate the caller's resources, starving every other downstream of attention. With bulkheads, each downstream gets its own pool, and a fault in one downstream cannot bleed into another.

The first step is to enumerate the downstreams and the shared resources. The caller may share a connection pool across all downstreams, or it may share a thread pool, or both. Each shared resource is a candidate for partitioning. The second step is to partition the pool. In a JVM application, this is often a separate `HystrixThreadPool` per downstream, configured with a maximum size and a bounded queue. In a Go service, this is often a semaphore per downstream. In a Cloudflare Worker, this is often a per-downstream concurrency cap inside `ctx.waitUntil`.

The third step is to choose the rejection policy. The default is fail-fast: when the bulkhead is saturated, the caller receives an immediate error and decides what to do (fallback, return cached value, return error to the user). The alternative is bounded queueing: when the bulkhead is saturated, the request waits in a queue. Bounded queueing is risky because it turns the bulkhead into a delay line, but it can be useful for traffic that the system is willing to hold briefly.

The fourth step is to make the bulkhead observable. Without metrics on pool utilisation, queue depth, and rejection rate, a bulkhead silently degrades into a slow failure. The metrics must be emitted in real time and alerted on when they cross thresholds.

The fifth step is to design for failure. The bulkhead must reject requests under saturation, and the caller must handle the rejection. The caller must not retry into the bulkhead; retry traffic would only make the saturation worse. The caller must apply a different policy (fallback, circuit breaker) when the rejection is sustained.

Server-side bulkheads are equally important. Each service instance has a finite number of concurrent requests it can serve, and a noisy-neighbour upstream can exhaust that capacity. Server-side bulkheads take the form of bounded executor pools, bounded queues with shedding policies, and per-tenant concurrency limits enforced at the edge of the service. Cloudflare Workers' per-tenant concurrency budgets, Durable Object input gates, and per-D1 connection limits are examples of runtime-enforced bulkheads.

## Controls

Bulkhead controls cover pool sizing, queue policy, and rejection instrumentation. Pool sizing should be deliberate and derived from the downstream's expected latency and the caller's tolerance for in-flight requests. Queue policy should be no queue by default; if a queue exists, it must be bounded and have a shedding policy. Rejection instrumentation must emit a counter and a structured log entry whenever a request is rejected, with enough context (downstream, tenant, pool size, queue depth) to debug later.

The bulkhead must also be configured against overload. If the bulkhead is set so tight that legitimate traffic is rejected, the bulkhead becomes a self-inflicted outage. Runbooks must define how to lift a bulkhead in an emergency and how to detect when lifting it is the wrong response.

## Validation evidence

Validation must prove that the bulkhead actually contains faults. The standard test drives the downstream into saturation and observes the caller's behaviour: only the downstreams in the same bulkhead should degrade; other downstreams should remain at their baseline. Without this test, the bulkhead is decorative.

Validation must also prove that the bulkhead does not silently turn saturation into slow failures. Rejection latency should be in milliseconds, not seconds. Synthetic tests should include a steady-state test (bulkhead sits at 30 percent utilisation) and a saturation test (one downstream fails; other downstreams are unaffected; rejections are visible in metrics).

## Failure modes and correction

The dominant failure is an undersized pool that was never tuned. The bulkhead rejects too often under normal load and the team removes it "to fix performance," reintroducing the original risk. The cure is to right-size the pool against the SLO and to make the rejection rate itself a SLO. A second failure is a shared bulkhead for unrelated downstreams. Two downstreams with very different traffic profiles share one pool and starve each other. The cure is one pool per downstream and, where appropriate, one pool per tenant or per priority class.

A third failure is the bulkhead turning into a queue. A bounded queue in front of a saturated pool does not stop the failure, it just delays it. The cure is to fail fast at the pool boundary. A fourth failure is the bulkhead not being enforced at all in the failure path. The cure is to make the bulkhead wrap the entire call path, including timeout and exception handling.

A fifth failure is a per-tenant bulkhead that cannot be enforced because the runtime does not expose the isolation primitive. The cure is to enforce the partition at the application layer with discipline, or to migrate to a runtime that exposes the primitive (Cloudflare Workers' per-tenant concurrency budgets, Durable Object input gates).

## Limitations

Bulkheads are necessary but not sufficient. They do not heal the downstream that is failing; they only contain the failure to its own compartment. A bulkhead also adds memory and connection overhead: each pool has its own minimum resource footprint. Bulkheads do not replace capacity planning; a bulkhead sized for half the production load will reject half the production load. Finally, bulkheads cannot protect against faults that originate inside the bulkhead itself—a bug in the pool implementation, an exhaustion of file descriptors, a runtime bug that holds a slot indefinitely.

## Canonical sources

- Microsoft Azure Architecture Center — *Bulkhead pattern*: https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead
- Netflix Hystrix repository, the origin of the bulkhead pattern in distributed systems: https://github.com/Netflix/Hystrix
- Chris Richardson — *Microservices Patterns* (Manning), the bulkhead pattern entry: https://microservices.io/patterns/reliability/circuit-breaker.html (catalogued alongside related reliability patterns)
- Microsoft — *Azure Architecture Framework*, Reliability pillar, on isolation as a cross-cutting concern
