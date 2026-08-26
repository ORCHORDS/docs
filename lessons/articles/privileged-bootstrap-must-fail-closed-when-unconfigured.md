# privileged-bootstrap-must-fail-closed-when-unconfigured

**Issue:** auth-bootstrap-credential-set
**Date:** 2026-08-20
**Author:** the platform team
**Status:** fixed (knowledge-base correction)

## Symptom

A service is migrating from a legacy shared secret to a bound cryptographic
identity, but its startup guard still requires the legacy secret. The newer
authentication path therefore cannot enrol or start on its own even though
request-time code already supports it. A related failure mode catches a signing
error, falls back to an absent secret, and sends an empty `Authorization:
Bearer` credential.

A second, subtler failure mode treats **identity metadata** as proof that the
identity is usable. For example, a cached record can contain a valid-looking
bound node/account identifier while its private key is truncated, malformed,
non-canonical Base64, the wrong raw length, or no longer matches the stored
public key. Startup then declares the cryptographic path viable and the first
protected request fails only when signing is attempted.

## Root cause

Bootstrap and request-time authentication evaluate different credential sets.
The bootstrap code asks whether one historical environment variable exists;
the request code asks whether any supported authenticator can produce a valid
credential. During a staged migration, the security boundary is the **set of
viable authentication paths**, not the presence of one particular legacy
credential.

Viability must include the **actual cryptographic material**, not only the
binding metadata. A bound principal ID plus unusable key bytes is not a viable
cryptographic identity. Persisted key material must survive strict decoding,
format/length checks, key construction, and—when both halves are stored—a
private→public consistency check before bootstrap counts that path as usable.

Fail closed when **no supported path is viable**. Do not fail merely because a
deprecated path is absent, and do not turn a failed preferred path into an
empty or malformed fallback. RFC 6750 defines a Bearer credential with a
non-empty token (`b64token = 1*(...)`), so `Authorization: Bearer ` is not a
valid authenticated request. NIST SP 800-63B permits multiple authenticators to
be bound during their lifecycle and requires an explicit migration plan when
an authenticator is being replaced.

Python's `base64.b64decode()` defaults to `validate=False`, which discards
non-alphabet characters before its padding check; persisted credential parsing
that requires canonical input should opt into strict validation. The
`cryptography` Ed25519 API requires exactly 32 raw private-key bytes and raises
`ValueError` when the raw private key has the wrong length.

**Sources:**
- [NIST SP 800-63B — Authenticator binding and lifecycle](https://pages.nist.gov/800-63-4/sp800-63b.html#authenticator-event-management)
- [RFC 6750 §2.1 — Authorization request header field](https://www.rfc-editor.org/rfc/rfc6750.html#section-2.1)
- [Firebase — Verify ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Firebase Admin SDK — ID-token expiration](https://firebase.google.com/docs/reference/admin/node/firebase-admin.auth.decodedidtoken#decodedidtokenexp)
- [RFC 9421 §7.2.2 — Signature replay](https://www.rfc-editor.org/rfc/rfc9421.html#section-7.2.2)
- [Python `base64.b64decode()` — strict validation](https://docs.python.org/3/library/base64.html#base64.b64decode)
- [`cryptography` Ed25519 — raw private-key loading](https://cryptography.io/en/45.0.7/hazmat/primitives/asymmetric/ed25519/)

## Fix pattern

1. Load and validate every supported credential source before deciding whether
   startup can continue. For persisted asymmetric identities, this means more
   than checking that a file and bound identifier exist:
   - strictly decode the persisted representation (for Python Base64, use
     `validate=True` when canonical Base64 is required);
   - enforce the algorithm's exact raw key sizes and construct the key object
     using the crypto library rather than trusting byte-string truthiness;
   - validate the bound principal/node identifier independently;
   - when a public key is persisted alongside the private key, derive the public
     key from the parsed private key and compare it to the stored public key;
   - treat any failure as an unavailable identity path and follow the explicit
     recovery/re-enrolment or legacy-fallback policy.
2. Represent viability explicitly instead of using truthiness of a single
   secret or a single metadata field:
   - a non-empty, validated legacy credential;
   - a parseable, internally consistent, already-bound cryptographic identity;
   - or an enrolment credential plus the local cryptographic capability required
     to create and bind a new identity.
3. Exit before protected network activity only when none of those paths is
   viable.
4. Enrol before the first signed protected request when enrolment is the only
   viable path. Verify the enrolment token server-side, including signature,
   issuer, audience, and expiration. Firebase ID tokens are short-lived and
   are issued with up to a one-hour expiration; do not treat their mere
   presence as proof that enrolment can succeed.
5. When the preferred authenticator fails at request time:
   - use the legacy fallback only when it is actually present and valid;
   - otherwise return an explicit authentication error or retry the preferred
     path according to a bounded policy;
   - never emit an empty credential, silently downgrade to anonymous access,
     or continue as though authentication succeeded.
6. For challenge-response signatures, bind the signature to the relevant
   message components and use a unique nonce and bounded lifetime so a captured
   signature cannot be replayed.
7. Log the selected path and failure class without logging secrets, bearer
   values, private keys, enrolment tokens, or complete signatures.

## Migration state matrix

| Available state | Startup | Protected request behavior |
|---|---|---|
| Valid legacy credential only | Allow | Use the legacy path |
| Bound cryptographic identity with validated signing material only | Allow | Sign each request; no legacy dependency |
| Enrolment credential + working crypto only | Allow | Enrol first, persist the bound identity, then sign |
| Bound identity + legacy credential | Allow | Prefer signing; use the legacy path only as the documented fallback |
| Bound identity metadata + malformed/unusable signing material + valid legacy credential | Allow only through the explicit legacy fallback/recovery policy | Do not attempt the broken signing path as though it were healthy; use the documented fallback and repair/re-enrol the identity |
| Bound identity metadata + malformed/unusable signing material + no fallback | Do not treat the identity as viable | Recover/re-enrol or exit before protected work |
| Signing fails + valid legacy credential | Continue only under the explicit fallback policy | Use the legacy credential and emit a non-secret diagnostic |
| Signing fails + no valid legacy credential | Do not send the protected request | Return/retry with an explicit authentication failure |
| No viable credential path | Exit before protected work | Send nothing |

## Anti-patterns

- Checking only `if not LEGACY_SECRET: exit(1)` before loading the replacement
  identity or enrolment configuration.
- Treating `nodeId != null`, `accountId != null`, or “key file exists” as proof
  that a signing identity is usable without parsing/validating the key material.
- Using permissive Base64 decoding for persisted private-key material and then
  checking only whether the resulting byte string is non-empty.
- Generating an `Authorization` header by interpolating a nullable or empty
  fallback value.
- Treating a configured enrolment token as valid without server-side token
  verification.
- Keeping an undocumented permanent downgrade path after the migration's
  observation window.
- Deleting the legacy path before fresh-node enrolment and existing-node
  identity loading have both been exercised end to end.
- Logging credentials to prove which path ran.

## Verification

- **Legacy-only:** startup and one protected request succeed unchanged.
- **Bound-identity-only:** startup succeeds with the legacy credential absent;
  the request uses the cryptographic path.
- **Fresh enrolment only:** startup creates and binds an identity, persists it,
  and completes a protected request without the legacy credential.
- **No credentials:** startup exits non-zero before protected network work and
  names the supported configuration choices without printing values.
- **Corrupt or unavailable identity:** behavior is explicit and tested; it does
  not silently authenticate as a different identity.
- **Strict persisted-key parsing:** malformed/non-canonical Base64, wrong raw
  Ed25519 key length, an invalid bound identifier, and private/public mismatch
  are each rejected as a viable identity before the first protected request.
- **Forced signing failure with fallback:** the valid fallback is used and the
  failure is observable without secret material.
- **Forced signing failure without fallback:** no `Authorization` header is
  sent and the caller receives a clear authentication failure.
- **Replay:** a previously accepted signed request or nonce is rejected.
- **Retirement gate:** remove the legacy credential only after enrolment,
  identity-only startup, normal signed traffic, failure handling, rollback,
  and the required observation window have reproducible evidence.

## Gotchas

- “Fail closed” applies at the authorization boundary. Requiring a retired
  credential when another verified credential is available is an availability
  bug, not additional security.
- A key file existing on disk does not prove that it is parseable, bound to the
  expected principal, accepted by the verifier, or stored with adequate local
  permissions.
- A valid-looking bound ID does not rescue invalid key bytes; bootstrap must
  validate the signer, not just the identity label.
- Python Base64 decoding is permissive by default (`validate=False`); strict
  persisted credential formats need an explicit strict decode step.
- Raw Ed25519 private keys are fixed-size material. A decoder returning “some
  bytes” is not enough; construct the key with the crypto library and handle
  its validation failure before marking the path viable.
- An enrolment token is a bootstrap credential, not the long-term per-request
  credential. Minimize its lifetime and use it only for the binding operation.
- Compatibility fallbacks need a removal condition and telemetry; otherwise a
  temporary migration bridge becomes permanent shared-secret debt.

## Related

- `security/secret-rotation.md`
- `patterns/feature-flags.md`
- `security/oauth-token-lifecycle.md`
- `testing/auth-flow-testing-strategy.md`
