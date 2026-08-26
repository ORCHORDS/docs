# HTTP message signatures: component coverage and replay control

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [RFC 9421: HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421.html)

## Problem

TLS protects an individual connection, but a message can pass through TLS-terminating gateways or intermediaries. HTTP message signatures can provide integrity and authenticity for selected request components, but a signature is only meaningful when it covers the right components and has replay controls.

## Practice

- Define a signature profile per endpoint: required covered components, permitted algorithms, key lookup, creation time, expiry, nonce, and replay window.
- Cover the method, authority or target URI, and security-relevant headers. When body integrity matters, cover a digest of the content rather than assuming headers protect it.
- Verify against the exact application semantics after proxy normalization; reject ambiguous duplicate fields and unsupported component forms.
- Enforce a bounded creation and expiry time, and store nonces or request IDs for the replay window on non-idempotent endpoints.
- Bind keys to known senders and permitted algorithms; reject algorithm downgrade and key-ID confusion.
- Keep TLS enabled: HTTP message signatures add application-level integrity but do not provide confidentiality.

## Verification

1. Modify the method, target, signed header, unsigned header, and body independently; confirm the intended changes are detected.
2. Replay a valid signed non-idempotent request inside and outside the replay window; both must follow policy.
3. Pass signed requests through the production gateway path and confirm signer and verifier construct compatible components.
4. Present a valid signature from an unauthorized key or algorithm; it must fail.

## Failure modes

- Signing only a timestamp or one header leaves method, target, or body semantics mutable.
- Validating a signature without application-specific requirements accepts insufficient coverage.
- Treating a signature as encryption leaks sensitive message content.

## Related

- [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421.html)
