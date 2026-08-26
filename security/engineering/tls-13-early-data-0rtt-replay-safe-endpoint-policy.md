# TLS 1.3 early data: 0-RTT replay-safe endpoint policy

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [RFC 8446: TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)

## Problem

TLS 1.3 0-RTT reduces connection setup latency, but early data can be replayed by an attacker. Transport-level encryption does not make an early request safe to repeat.

## Practice

- Disable 0-RTT by default for authenticated, state-changing, payment, quota, administrative, and one-time-token endpoints.
- If enabling it, restrict acceptance to demonstrably idempotent read operations with no security-sensitive side effects.
- Make the 0-RTT acceptance decision at the edge and propagate that state to the application so it can reject unsafe methods and routes.
- Do not assume idempotency keys alone make an operation suitable: replay can still consume rate limits, trigger notifications, or reveal timing and data.
- Test behavior when early data is rejected; clients must safely retry after the handshake without duplicating application effects.
- Monitor early-data acceptance, rejection, and any attempted use on forbidden routes.

## Verification

1. Send early-data requests to every mutating and privileged route; all must be rejected before side effects.
2. Replay an allowed early-data request from different network paths and confirm the result is safe and equivalent.
3. Force the server to reject early data and confirm the client retries only when safe.
4. Inspect edge and application logs for an explicit early-data marker and forbidden-route alerts.

## Failure modes

- Treating 0-RTT as ordinary TLS causes replay of irreversible operations.
- Allowing an unsafe route at the edge leaves application code unable to distinguish early data.
- Retrying a rejected request blindly duplicates a non-idempotent operation.

## Related

- [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446.html)
