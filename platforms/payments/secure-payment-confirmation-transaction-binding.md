# Secure Payment Confirmation transaction binding

**Issue:** A checkout reuses an ordinary WebAuthn login assertion as proof that a customer approved a particular payment. The assertion does not visibly bind the payee and amount, a stale challenge can be replayed, and the server treats browser UI completion as settlement.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** emerging web standard; feature-detect and retain fallback

## Problem and applicability

Secure Payment Confirmation (SPC) combines a payment credential with user-agent-controlled confirmation UI for transaction details. The resulting assertion is designed to cryptographically bind confirmation context such as the relying party, challenge, origin, payee, instrument, and amount represented in the flow.

Use SPC only with a participating payment ecosystem and current browser support. It augments payment authentication; it does not authorize capture at a processor, prove funds, or replace the order and ledger state machine.

## Controls and implementation

1. Create payment credentials through the documented SPC/WebAuthn registration flow with explicit relying-party ownership and account linkage. Keep payment credentials separate from assumptions attached to a generic sign-in credential.
2. Generate a high-entropy, single-use server challenge for one checkout attempt. Store its order, customer/session, amount, currency, payee, expiry, and consumed state atomically.
3. Construct the SPC request from server-authoritative transaction data. The client may render a cart, but it must not choose the signed amount or payee.
4. Invoke the request only from the allowed user gesture and origin context. Configure any required Permissions Policy narrowly for framed payment participants; do not grant broad cross-origin access.
5. On the server, verify assertion type, challenge, origin, relying-party identifier, credential identifier, signature, authenticator data, and transaction fields according to the current specification and WebAuthn validation rules.
6. Consume the challenge exactly once in the same transaction that records the verified confirmation. Reject expiry, replay, field mismatch, unknown credentials, and unsupported algorithms.
7. Submit authorization or confirmation to the PSP with its own idempotency key. Move the order only from authoritative PSP API/webhook results, not from the SPC UI completing.
8. Provide a clear alternative authentication/payment path for unsupported browsers, unavailable authenticators, cancellation, and issuer-required challenge.

## Verification

Test feature absent, credential creation and lookup, wrong origin/RP, changed payee/amount/currency, stale and replayed challenge, cloned client payload, invalid signature, authenticator cancellation, iframe policy denied, PSP decline after valid confirmation, duplicate backend submission, and fallback authentication.

Confirm the user-agent-controlled display matches the server record byte-for-byte where the specification defines the value, and that one verified assertion cannot approve a second order.

## Gotchas

- SPC availability is ecosystem- and browser-dependent; capability detection is not proof a credential exists.
- Authentication success is not payment authorization, capture, or settlement.
- Displayed instrument information is descriptive and must not be accepted as a server account identifier without validation.
- The standard is evolving; pin test vectors and review changes before rollout.

## Official sources

- [W3C — Secure Payment Confirmation](https://www.w3.org/TR/secure-payment-confirmation/)
- [W3C — Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/)
