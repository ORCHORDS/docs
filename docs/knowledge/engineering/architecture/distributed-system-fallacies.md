# distributed-system-fallacies

**Issue:** Common false assumptions engineers make when designing distributed systems
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Systems designed as if they were local applications fail unpredictably in production.

## Pattern / Solution
The 8 Fallacies of Distributed Computing (Deutsch et al.):

1. The network is reliable
2. Latency is zero
3. Bandwidth is infinite
4. The network is secure
5. Topology does not change
6. There is one administrator
7. Transport cost is zero
8. The network is homogeneous

Counter-design for each:
- Retries with idempotency for (1)
- Async/non-blocking for (2)
- Pagination and compression for (3)
- mTLS and zero-trust for (4)
- Service discovery for (5)
- Policy-as-code for (6)
- Batching for (7)
- Protocol negotiation for (8)

## Gotchas
- Adding retries without idempotency makes fallacy (1) worse
- Ignoring serialization cost leads to surprise bandwidth bills
- Teams often discover fallacy (4) after a breach, not before

## Related
- `idempotency-design.md`
- `retry-pattern.md`
- `zero-trust-architecture.md`
