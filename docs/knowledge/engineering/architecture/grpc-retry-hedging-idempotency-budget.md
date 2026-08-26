# gRPC retry and hedging idempotency budget

**Issue:** gRPC retry and request hedging can improve tail latency, but each additional attempt consumes server capacity and can repeat side effects. Transport configuration cannot determine whether an application operation is safe to execute more than once.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Classify each method as replay-safe, conditionally replay-safe with an idempotency key, or non-replay-safe before assigning a retry or hedging policy.
- Prefer one bounded policy per method; do not combine independent proxy, client, and service retries without a shared end-to-end attempt budget.
- Set maximum attempts, per-attempt timeout where supported, backoff, retryable or non-fatal status codes, and an overall request deadline explicitly.
- Configure retry throttling so widespread failures suppress extra attempts instead of multiplying load.
- Propagate a stable operation identifier and deduplicate committed mutations durably on the server.
- Emit attempt number, hedge count, committed outcome, deadline, and final status without duplicating business-success metrics.

## Implementation and tests

Deliver the policy through the gRPC service configuration and verify the selected client library supports every field. For hedging, choose a delay from measured latency distributions rather than sending all copies immediately. Cancel losing attempts once a response commits, while assuming cancellation may arrive after server work has begun.

Inject pre-commit transport failure, post-commit response loss, retryable application status, non-fatal hedging status, deadline expiry, and a retry storm. Assert the attempt ceiling, single durable side effect, throttle activation, cancellation cleanup, and final status.

## Gotchas and applicability

gRPC may perform limited transparent retries even without an explicit application policy. Once response headers are received, an RPC is committed for retry purposes; that boundary is not the same as a database commit. Hedging lowers latency by intentionally increasing concurrent work and can worsen an overloaded service.

Status codes are not universally safe retry signals. The application’s mutation and deduplication design remains authoritative.

## Official sources

- [gRPC: Retry](https://grpc.io/docs/guides/retry/)
- [gRPC: Request hedging](https://grpc.io/docs/guides/request-hedging/)
- [gRPC: Service config](https://grpc.io/docs/guides/service-config/)
