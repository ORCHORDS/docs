# COSE critical protected-header enforcement

**Issue:** A COSE verifier ignores or only syntactically parses a header named in `crit`, allowing a signer-required security condition to be skipped while the cryptographic signature or tag still verifies.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Contract

RFC 9052 defines `crit` as COSE header label 2. When present, it must be in the protected-header map and contain at least one label. Every listed label must also be present in that protected map, and the application or security library must understand and process it. A missing listed parameter is a fatal processing error.

## Controls

- Decode CBOR and COSE with canonical bounds on message size, nesting, collection length, and integer range.
- Reject duplicate labels in either header map and reject a security-relevant label appearing in both protected and unprotected maps.
- Require `crit` itself to be protected, an array, non-empty, and free of duplicate labels.
- For every listed label, require the parameter in the protected map and dispatch to an explicit supported semantic handler.
- Fail closed on an unknown, disabled, malformed, context-inapplicable, or unprocessed critical parameter.
- Apply application policy after cryptographic verification, including algorithm, key use, content type, countersignature, freshness, and external authenticated data.
- Authenticate `alg` wherever the COSE construction permits and pin allowed algorithms to key and use case.
- Record only safe parameter identifiers and failure classes; do not log plaintext, keys, or unauthenticated data as trusted context.

## Verification

Maintain negative vectors with `crit` in the unprotected map, an empty list, a missing referenced label, unknown labels, duplicates, wrong value types, a recognized-but-disabled feature, and a handler that parses without enforcing semantics. Each must fail before payload use. Cross-test vectors across every producer and verifier implementation.

## Gotchas

Recognizing a label name is not understanding it. The enforcing component must apply the parameter's semantics in the current message context. Header parameters defined by RFC 9052 generally need not be listed in `crit`, and application profiles can define additional omission rules; document those rules rather than accepting arbitrary omission.

## Official sources

- [RFC 9052: COSE Structures and Process](https://www.rfc-editor.org/rfc/rfc9052.html#section-3.1)
- [IANA COSE Header Parameters registry](https://www.iana.org/assignments/cose/cose.xhtml#header-parameters)
