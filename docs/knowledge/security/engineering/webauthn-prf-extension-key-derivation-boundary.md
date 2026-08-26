# WebAuthn PRF extension key-derivation boundary

**Issue:** The WebAuthn `prf` extension can return a stable, credential-associated 32-byte pseudorandom result for an input, enabling client-side key derivation. That result is key material: serializing the complete credential with `PublicKeyCredential.toJSON()` includes PRF results when present and can unintentionally send a client-only encryption secret to the relying-party server.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented — WebAuthn Level 3 Candidate Recommendation

## Controls

- Check client and authenticator capability; support absence of `prf` without weakening an encrypted-data policy silently.
- Use `eval` for a common input or `evalByCredential` only with a non-empty `allowCredentials` list during authentication.
- Treat returned `first` and optional `second` buffers as secret key material: keep them in memory briefly, zero application-owned copies where practical, and never log, persist in plaintext, or place in telemetry.
- Derive purpose-specific keys from the PRF result with a reviewed KDF and unique context; do not reuse raw output across encryption, authentication, and wrapping purposes.
- Manually construct the server-bound WebAuthn response when PRF output is client-only; do not send the unfiltered `toJSON()` result.
- Define credential loss, rotation, multi-credential recovery, and encrypted-data rewrapping before using the PRF as a data key root.
- Bind ciphertext metadata to credential ID, derivation version, algorithm, input identifier, and account context without storing the PRF result.

## Implementation and tests

Request extension enablement during registration, but expect that some authenticators cannot evaluate the PRF until an assertion. During authentication, choose the input deterministically, derive a scoped key locally, and exclude PRF results from the payload sent to the server.

Test unsupported clients, enabled-without-results registration, assertion results, `evalByCredential` selection, wrong credential, equal and distinct inputs, passkey replacement, sync or recovery scenarios, page reload, and accidental generic serialization. Inspect network traces and crash reports for output bytes.

## Gotchas

Extension support is per client and authenticator. PRF output is associated with a credential, so losing every usable copy can make client-encrypted data unrecoverable. A server that receives the output can derive the same application keys and defeats a client-only trust boundary.

WebAuthn Level 3 is a Candidate Recommendation and implementation coverage varies. Verify current platform behavior.

## Official sources

- [W3C WebAuthn Level 3: PRF extension](https://www.w3.org/TR/webauthn-3/#prf-extension)
- [W3C WebAuthn Level 3: PublicKeyCredential.toJSON](https://www.w3.org/TR/webauthn-3/#dom-publickeycredential-tojson)
