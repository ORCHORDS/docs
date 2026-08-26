# irreversible-fulfillment-must-follow-atomic-claim

**Issue:** A workflow performs an irreversible side effect after attempting a conditional state claim, without checking whether the claim actually succeeded.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Lesson

A compare-and-swap or guarded update is the concurrency gate only if the code checks its affected-row result. Executing fulfilment, credit creation, or notification after a losing claim can produce an irreversible side effect for a workflow the caller did not own.

This lesson comes from [example-org/example-repo commit <commit-sha>](https://github.com/example-org/example-repo).

## Apply

- claim the state with a conditional mutation;
- check the affected-row/result count before every dependent irreversible action;
- treat a lost claim as a normal concurrency outcome, not an error to compensate blindly;
- make downstream effects idempotent and record a reconciliation state;
- test simultaneous contenders and termination between claim and effect.

## Verification

- Only the successful claimant creates the fulfilment record.
- A losing contender has no externally visible side effect.
- Retrying after a crash follows a deterministic recovery path.
- Race tests run repeatedly, not once.

## Related

- `patterns/idempotency-reservation-lease-recovery.md`
- `payments/nowpayments-callback-payment-intent-integrity.md`
