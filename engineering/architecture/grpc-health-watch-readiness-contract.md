# gRPC health Watch readiness contract

**Issue:** A process can accept TCP connections while its gRPC service is not ready. One-shot polling also misses transitions and can create a synchronized readiness storm, while the standard health `Watch` RPC provides a streaming service-state contract.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Implement the standard gRPC Health Checking service and publish status for every routed service name, not only the empty overall-server name.
- Set `NOT_SERVING` before draining dependencies or removing capacity, and update health state independently of process liveness.
- Enable client-side health checking through the service configuration when the client implementation supports it.
- Bound reconnect backoff and readiness deadlines; do not replace an unavailable health stream with unlimited request retries.
- Protect the health endpoint against unauthenticated topology disclosure where it is reachable outside the trusted network.

## Implementation and tests

Register the health service during server startup, initialize services to a non-serving state, and publish `SERVING` only after required dependencies and migrations are usable. During shutdown, publish `NOT_SERVING`, allow clients to observe it, drain active calls, and then stop.

Test initial unknown and not-serving states, a transition to serving, dependency loss and recovery, server restart, stream cancellation, load-balancer reconnection, and an implementation that returns `UNIMPLEMENTED` for `Watch`. Confirm user RPCs are not sent to a subchannel that client-side health checking has marked unhealthy.

## Gotchas and applicability

Health is a declared routing signal, not proof that every request will succeed. A dependency check can amplify an outage, so distinguish critical readiness dependencies from diagnostics. Not all client libraries enable health checking automatically, and behavior for unsupported `Watch` must be verified in the selected gRPC implementation.

Liveness should remain simple enough to let an orchestrator restart a wedged process; readiness may express richer service availability.

## Official sources

- [gRPC: Health checking](https://grpc.io/docs/guides/health-checking/)
- [gRPC health checking protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md)
