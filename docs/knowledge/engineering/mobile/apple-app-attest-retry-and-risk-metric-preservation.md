# Apple App Attest Retry and Risk-Metric Preservation

**Issue:** Generating a new App Attest key or challenge after a transient service failure can weaken device risk continuity, create orphan keys, and make legitimate clients look like repeated fresh devices.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Generate App Attest keys on the device, but issue short-lived, single-purpose challenges from the server and bind the client-data hash to the intended operation.
- Send the attestation object to the server and perform all verification there. Never accept a client-side “verified” boolean.
- When attestation returns `serverUnavailable`, retry later with the same key and the same client-data hash. Persist only the minimum retry state needed to preserve continuity and expire it with the challenge.
- Do not generate replacement keys on generic network failures. Classify unsupported-device, invalid-input, invalid-key, and transient-service errors separately.
- Associate a key identifier with an account or installation only after successful server verification. Discard it after a definitive verification failure.
- Rate-limit key generation and attestation attempts, monitor repeated fresh-key behavior, and feed that behavior into risk decisions rather than an unconditional block.
- Protect challenges against replay and ensure production and development App Attest environments are not mixed.

## Verification

1. Simulate `serverUnavailable`, process restart, offline retry, expired challenge, invalid key, duplicate response, and successful retry.
2. Assert transient retries reuse the exact key identifier and client-data hash.
3. Assert no account binding occurs before server verification and a consumed challenge cannot be reused.
4. Track keys generated per installation, attest success by error class, retry recovery, and risk-policy outcomes.

## Gotchas

- App Attest helps assess app integrity; it does not replace user authentication or transaction authorization.
- Retry state must not outlive its challenge.
- Unsupported devices need an explicit, risk-based fallback path.

## Sources

- [Apple DCAppAttestService attestKey documentation](https://developer.apple.com/documentation/devicecheck/dcappattestservice/attestkey(_:clientdatahash:completionhandler:))
- [Apple DCError serverUnavailable documentation](https://developer.apple.com/documentation/devicecheck/dcerror-swift.struct/serverunavailable)
