# iOS App Attest Device Integrity Assertions

Apple's App Attest service lets your server verify that a request came from a genuine, uncompromised instance of *your* app on a genuine Apple device — not a script, not a repackaged build, not an emulator farm. The device generates an attestation key in the Secure Enclave, Apple countersigns a certificate binding that key to your app identity, and each sensitive request carries a signed assertion your server verifies. It is one of the strongest anti-abuse signals available to iOS-backed services, and it is a protocol with real ceremony: attestation once, assertions per request, with clock windows and replay protection to honor. This article covers the attestation and assertion flows, server-side verification steps, and the operational decisions (enforcement modes, key rotation, failure handling) that determine whether the signal is usable.

## Scope

This article addresses Apple's App Attest (DeviceCheck framework, DCAppAttestService): key generation and attestation on device, the assertion generation API, server-side verification of attestation objects and assertions (certificate chain to Apple's App Attest root, challenge nonces, counter monotonicity, App ID binding), and enforcement policy design. It covers the protocol and integration. It does not cover DeviceCheck bits (per-device ephemeral state), Managed App Attest distribution, or general API-auth design.

## Workflow or implementation guidance

The protocol has two phases.

**Phase 1 — Attestation (once per install, or per key lifetime):**

1. Device: `DCAppAttestService.shared.generateKey()` returns a key identifier.
2. Server: on receiving an attestation request, generate a one-time challenge (32 random bytes), store it with TTL, return it.
3. Device: `attestKey(challenge)` returns an attestation object: the key's certificate chain (leaf signed by Apple's App Attest CA, intermediate, root anchored), the challenge embedded, and the App ID (Team ID + bundle ID) hashed into the credential.
4. Server verifies:
   - Cert chain validates to Apple's App Attest root (downloadable from Apple's documentation) for the *current* root; roots rotate — pin the current root and track Apple announcements.
   - The challenge inside matches the issued one (proving freshness, not replay).
   - The App ID in the attestation equals your app's (`TEAMID.BundleID`) — otherwise someone is attesting a different app's key to you.
   - Decode the credential ID/public key; store the public key server-side keyed to the user/device with the attestation's counter (initially 0).

**Phase 2 — Assertions (per sensitive request):**

1. Server: issue another one-time challenge for the request.
2. Device: `generateAssertion(challenge)` signs (with the Secure Enclave key) a structure containing the challenge, the key identifier, and a monotonically increasing counter (`signCount`).
3. Server verifies:
   - Recover the stored public key for that key ID; verify the signature over the assertion's authenticator data.
   - Challenge matches the issued one (freshness).
   - `signCount` strictly greater than the stored value — the replay defense: a cloned/replayed assertion reuses a counter and fails.
   - Update the stored counter.

API-shape details that matter: `generateKey`/`attestKey`/`generateAssertion` can each fail with `DCError` codes — unsupported device (`DCError.notSupported` on older hardware/OS), rate-limited (`DCError.serverRejected` family), key-invalidated. The app must treat "not supported" as a first-class capability branch, not an error: App Attest requires modern hardware/OS; your enforcement policy needs a path for the rest. Rate limits exist server-side at Apple for attestations per key/device — batch-attesting on every launch will hit them; attest lazily at the moment of a sensitive action or once per install.

Enforcement policy — the decision that outranks the code:

- **Audit mode first.** Log verification outcomes (attested/not-attested/failure reason) alongside normal auth for weeks before denying anything. The distribution of failures (OS versions, jailbreak-tool users, plain bugs) tells you what enforcement will break.
- **Signal, not sole gate.** App Attest proves app+device genuineness at attestation time and key possession per request. Combine with auth: an attested-but-logged-out user still needs login; an unattestable-but-authentic older device shouldn't be bricked. Tier it: attested devices get higher limits, unattested get friction (step-up verification), only targeted abuse classes get hard denial.
- **Counter desync recovery.** If your stored counter exceeds the device's next assertion (server restored from backup, race in counter updates), every assertion fails. Store counters transactionally with the request that verified them; if desync occurs, the recovery is re-attestation — build the re-attest flow before you need it.
- **Key lifetime.** Attestation keys persist but can be invalidated (`DCError.keyInvalidated` on device changes/restores); the app regenerates and re-attests, and the server replaces the stored key after verifying the new attestation. Bind attestation state to the *account* (user re-attests after reinstall), not to a device identifier that can't be re-derived.

A worked example: a ticketing app's purchase endpoint sees scripted bulk buying. Integration: attest at first purchase attempt; assert on every purchase request with a per-request challenge. Enforcement rolls out in three stages — audit (2 weeks, measure failure distribution), friction (unattested users get CAPTCHA + rate limits), deny (specific abuse patterns with unattested+high-velocity signals). Result: script traffic now must run real apps on real devices with per-request Secure Enclave signatures; the economics of the abuse collapse without locking out the tail of legitimate older devices.

## Controls

- Challenges are single-use, server-generated, 32 bytes, with short TTL and per-endpoint scope; a challenge store with atomic claim-on-verify prevents double-spend of a challenge.
- Counters stored transactionally with verification outcomes (the assertion verify and counter update commit together or not at all); a re-attestation path exists and is tested before enforcement turns on.
- Apple root certificates pinned server-side with a rotation runbook (Apple publishes new roots; verification breaks silently-wide when they rotate — calendar the check).
- Audit-mode logging of every verification decision with reason codes for ≥2 weeks pre-enforcement; enforcement thresholds reviewed against that distribution, not guessed.
- Monitoring: assertion failure rate by OS version (capability gaps), counter-desync rate (infra bug signal), attestation success latency (Apple service health), and a kill switch to flip enforcement back to audit instantly.

## Validation evidence

- The App Attest protocol — `generateKey`, `attestKey`, `generateAssertion`, challenge embedding, App ID binding, certificate chain to Apple's App Attest root, counter semantics, and the documented server-side verification procedure with pseudocode — is specified in Apple's official documentation (DeviceCheck framework reference and the "Establishing your app's integrity" article on developer.apple.com).
- Apple publishes the App Attest root certificate and the verification steps including nonce and counter checks in the same documentation; the X.509 chain-validation mechanics follow standard path validation.
- A reproducible integration test: staging app instance attests with a server-issued challenge; server verifies attestation (chain, challenge, App ID), stores key+counter; the app generates an assertion for a second challenge; server verifies signature, challenge, and counter increment; then replay the same assertion and assert verification fails on counter — the replay defense demonstrated end-to-end against your own implementation.

## Failure modes and correction

- **Replay accepted.** Cause: counter not checked or not stored transactionally. Correct by strict-greater counter check with atomic storage.
- **Cross-app attestation accepted.** Cause: App ID not verified against your Team+Bundle. Correct by explicit App ID equality check during attestation.
- **Root rotation outage.** Cause: pinned old Apple root. Correct by rotation runbook and pinning the current root with a monitoring probe that validates a known-good attestation daily.
- **Legitimate users denied after rollout.** Cause: enforcement without audit distribution. Correct by audit-first policy and capability-tiered enforcement.
- **Counter desync lockouts.** Cause: non-transactional counter updates. Correct by transactional verify+update and tested re-attestation recovery.

## Limitations

- Requires supported hardware/OS; older device populations need a policy path (App Attest cannot be universal gate).
- Attestation certifies app integrity at attestation time; determined attackers on jailbroken devices attack around the margins (hooking before attestation), so treat the signal as raising cost, not as proof of all future behavior.
- Apple-side rate limits constrain attestation frequency; attest sparingly by design.
- The service verifies app authenticity, not user identity — pair with auth; it says nothing about account ownership.

## Canonical sources

- Apple, Establishing your app's integrity with App Attest (protocol, server verification, root certificate): https://developer.apple.com/documentation/devicecheck/establishing-your-app-s-integrity
- Apple, DeviceCheck framework reference (DCAppAttestService): https://developer.apple.com/documentation/devicecheck
