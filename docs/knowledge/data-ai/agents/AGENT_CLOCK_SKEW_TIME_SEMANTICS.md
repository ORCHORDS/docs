# Clock Skew and Time Semantics in Distributed Agents

## Scope

Agent workflows use time for deadlines, leases, cache freshness, credential validity, scheduling, and evidence. Treating all timestamps as interchangeable creates failures when hosts disagree, clocks jump, or messages arrive late. This article defines explicit time semantics for distributed agent orchestration. It complements timeout budgets and durable scheduling but focuses on clock selection, comparison, and uncertainty.

NIST provides guidance for synchronizing security-relevant clocks, while IETF Network Time Protocol specifications explain offset, delay, and clock discipline. HTTP defines date and age semantics for representations. These sources do not guarantee perfectly synchronized systems; the engineering goal is to make bounded uncertainty visible and avoid unsafe ordering assumptions.

## Workflow

1. Classify every time field as wall-clock instant, monotonic duration, logical sequence, lease expiry, or externally asserted time. Document its comparison rules.
2. Use a monotonic clock for local elapsed time and deadlines. Derive a remaining duration rather than repeatedly comparing wall-clock timestamps.
3. Synchronize wall clocks through an authenticated, monitored time service appropriate to the environment. Record synchronization health and estimated offset.
4. At admission, convert an external absolute deadline into a conservative local duration by subtracting transit allowance and clock-uncertainty margin. Reject already-expired or implausibly distant values.
5. Use server-issued sequence numbers or revisions to order state changes. Do not infer causal order solely from wall-clock timestamps.
6. For leases, store issuer, issue revision, expiry instant, and fencing token. A renewed lease receives a higher token so an old holder cannot commit after pause or partition.
7. Preserve source timestamps as claims, while separately recording local receipt and processing times.
8. When synchronization uncertainty exceeds policy, suspend operations whose safety depends on accurate wall time and continue only explicitly safe local-duration work.

## Controls, data, and evidence

Maintain an inventory of time sources, synchronization topology, authentication method, expected accuracy, alert thresholds, and fallback behavior. Prevent ordinary workloads from setting system time. Use multiple reliable sources where warranted and monitor offset, jitter, reachability, leap indicators, and correction events. A backwards wall-clock adjustment must never extend a monotonic timeout.

Time-bearing records should include timestamp value, format, timezone or UTC indication, clock source, uncertainty when available, local receipt time, and sequence or fencing token. Normalize exchange instants to a standard representation but retain the original claim when forensic meaning matters. Evidence includes configuration baselines, synchronization-health histories, chaos-test results, lease conflict tests, and decision records for uncertainty margins.

For HTTP caches, implement `Date`, `Age`, freshness lifetime, and validation according to protocol semantics rather than using local file modification times as substitutes. For signed tokens, apply a small documented skew allowance at the verifier; do not let each service invent a different tolerance.

## Validation tests

Move the wall clock backward during a running task and verify its monotonic deadline still fires. Move it forward and ensure leases are not committed without fencing checks. Inject offsets just below and above the allowed uncertainty; the boundary behavior must be deterministic. Suspend a worker beyond its lease, let another worker acquire a higher token, then resume the first and verify its write is rejected.

Deliver events out of timestamp order while preserving sequence numbers and confirm reducers follow the sequence. Send deadlines with missing timezone, excessive future horizon, invalid date syntax, and values that expire inside the uncertainty margin. Test leap-second handling according to the platform's documented behavior. Partition the time service, exhaust holdover, and confirm time-sensitive side effects enter the defined safe state. Compare recorded receipt times across a controlled trace to validate monitoring without asserting impossible perfect causality.

## Failure handling

When clock health degrades, raise a distinct `time_uncertain` condition. Stop issuing long leases, validating narrowly timed assertions, or performing irreversible scheduled actions if policy requires reliable wall time. Existing local monotonic deadlines can continue on the same process. After restart, they must be reconstructed conservatively from durable absolute data and uncertainty, or expired.

If conflicting writes reveal a fencing failure, isolate the affected resource, reject holders with stale tokens, reconcile state using authoritative revisions, and investigate all commits in the overlap. Never repair ordering by rewriting historical timestamps. If an upstream timestamp is malformed, retain it only as untrusted input and use receipt time for operational handling.

## Limitations

Clock synchronization reduces but never eliminates uncertainty. Monotonic clocks generally cannot be compared across hosts and may have platform-specific suspend behavior. Fencing requires the protected storage system to enforce tokens atomically. Sequence numbers establish order only within their issuing domain. Time controls do not solve replay, authorization, or business-calendar interpretation. Extremely disconnected agents need domain-specific rules for offline operation and reconciliation.

## Canonical sources

- **NIST, SP 800-53 Revision 5, AU-8 Time Stamps:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **IETF, Network Time Protocol Version 4 (RFC 5905):** https://www.rfc-editor.org/rfc/rfc5905.html
- **IETF, HTTP Caching (RFC 9111):** https://www.rfc-editor.org/rfc/rfc9111.html
