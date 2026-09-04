# Limited-Resource Concurrency and Locking Review

## Purpose

Verify that limited-quantity business resources cannot be double-booked, over-allocated, or consumed more than once by racing concurrent requests or manipulating transaction timing.

## Source basis

OWASP ASVS 5.0.0 requirement v5.0.0-2.3.4 requires business-logic locking mechanisms where limited resources such as seats or delivery slots could otherwise be double-booked. Requirement v5.0.0-2.3.3 also requires business operations to complete atomically or roll back to the previous correct state.

## Inputs

- inventory of limited or single-use resources;
- documented reservation, purchase, allocation, or redemption flow;
- persistence and transaction design;
- representative API routes or service operations;
- safe test data and concurrency tooling.

## Procedure

1. **Identify constrained resources.** List inventory items, seats, slots, quotas, coupons, one-time grants, balances, or other resources whose available quantity can reach zero.
2. **Map state transitions.** Document the transition from available to held, committed, released, expired, or cancelled.
3. **Locate the authority.** Confirm that the definitive availability decision is made by a trusted service and durable state, not only by browser or client state.
4. **Send concurrent claims.** Issue simultaneous valid requests for the last available unit and verify that at most the allowed number succeeds.
5. **Test duplicate retries.** Repeat identical or near-identical requests around timeouts and transient failures to confirm idempotency or equivalent duplicate protection.
6. **Test hold expiry.** Where temporary reservations exist, verify expiry and release cannot overlap with a late commit in a way that creates two owners.
7. **Test rollback.** Force a downstream failure after allocation begins and confirm partial state is rolled back or reconciled without leaking inventory.
8. **Review locking/transaction scope.** Confirm database transactions, conditional updates, optimistic concurrency, distributed locks, queues, or other mechanisms cover the actual race boundary.
9. **Test cross-node behavior.** If multiple application instances process the flow, ensure correctness does not depend on in-process memory or a node-local lock.
10. **Record residual risk.** Document unavoidable oversubscription tolerances, compensating controls, and reconciliation ownership where strict exclusivity is not required.

## Evidence

Record the tested resource, initial quantity, request concurrency, successful and rejected outcomes, transaction/log evidence, application revision, and any identified race window.

## Completion criteria

The review is complete when concurrent attempts cannot allocate beyond the allowed quantity, retries cannot duplicate a committed effect, partial failures restore a valid state, and the concurrency mechanism is effective across the real deployment topology.

## Sources

- OWASP ASVS 5.0.0, V2.3 Business Logic Security: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x11-V2-Validation-and-Business-Logic.md
- OWASP Web Security Testing Guide, Business Logic Testing: https://owasp.org/www-project-web-security-testing-guide/

## Scope note

The correct concurrency mechanism depends on the data store and architecture. This playbook tests the outcome rather than prescribing one locking technology.
