# JOSE Fully Specified Algorithm Identifiers

**Issue:** Polymorphic JOSE algorithm names can leave curve, hash, or parameter choices implicit, causing implementations to accept a different cryptographic suite than policy intended.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Prefer fully specified algorithm identifiers where the applicable JOSE profile defines them.
- Allowlist exact algorithms per issuer, key type, curve, and use case.
- Reject identifiers whose implied parameters conflict with JWK metadata or local policy.
- Record algorithm migrations and retain negative interoperability tests.

## Verification

- Swap curves or key types while retaining an ambiguous family identifier.
- Offer deprecated and fully specified identifiers in adversarial order.
- Verify producer and consumer agree on the exact cryptographic suite.

## Gotchas

- Algorithm allowlisting does not replace signature, claims, audience, and key-origin validation.
- Legacy ecosystems may require a staged migration from polymorphic identifiers.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9864.html
