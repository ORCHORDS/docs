# two-generals-problem

**Issue:** Understanding the fundamental impossibility of guaranteed agreement over unreliable channels
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams try to design systems that guarantee "exactly once" or "both agree" over a network, which is provably impossible in the general case.

## Pattern / Solution
Two armies must coordinate an attack but messengers can be captured. No finite number of confirmations is sufficient — the last confirmation always leaves one party uncertain.

Practical implications:
- TCP uses sequence numbers + ACK but operates on probabilistic reliability, not certainty
- Distributed commit protocols (2PC) work around the problem but trade availability
- Systems accept the impossibility and design for recovery:

```
Approach 1: Idempotent retries — if unsure, retry; receiver deduplicates
Approach 2: Timeouts + compensating actions — if no ACK, assume failure, undo
Approach 3: Leases — assume success lasts for T seconds; renew or expire
```

## Gotchas
- No protocol can guarantee agreement in the presence of arbitrary message loss
- 2PC does not solve the two generals problem; it only reduces the window of uncertainty
- Real-world systems choose "good enough" reliability (multiple retries) over mathematical certainty

## Related
- `idempotency-design.md`
- `at-least-once-delivery.md`
- `exactly-once-delivery.md`
