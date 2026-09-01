---
title: "JSON Canonicalization Scheme RFC 8785 Version Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# JSON Canonicalization Scheme RFC 8785 Version Governance

## Purpose

RFC 8785 defines the JSON Canonicalization Scheme (JCS), a deterministic representation of JSON data intended for cryptographic operations and other uses that require stable bytes. Ordinary JSON equivalence is not byte equivalence: member order, number formatting, escaping, and whitespace can differ without changing a parsed value.

This guidance governs profiles that adopt JCS. It does not assert that canonicalization makes untrusted JSON safe or that a signature proves the truth of the signed claims.

## Profile identity

A protocol using canonical JSON should identify:

- RFC 8785 as the canonicalization specification;
- the exact data model and schema accepted before canonicalization;
- the character encoding and transport framing;
- duplicate-member rejection behavior;
- permitted number ranges and precision constraints;
- signature, digest, or identifier algorithms applied to canonical bytes;
- domain-separation or context-binding rules; and
- how profile versions are represented and negotiated.

Do not label a custom stable serializer as JCS unless it conforms to RFC 8785. Give extensions or restrictions a separate profile identifier.

## Processing boundary

Canonicalization begins only after the input has passed syntax and profile validation. The application must preserve the data model expected by JCS and reject inputs that cannot be represented without semantic loss.

A safe processing sequence is:

1. Decode the transport using the required character encoding.
2. Parse JSON while detecting duplicate object member names.
3. Validate the schema, value domains, and profile restrictions.
4. Canonicalize the validated value with a conforming implementation.
5. Apply the digest or signature algorithm to the canonical bytes.
6. Bind the result to its protocol context and algorithm identifiers.
7. Compare or verify without reserializing through a different data model.

## Numbers and interoperability

JSON number handling is a major interoperability boundary. RFC 8785 relies on the ECMAScript number serialization model and the I-JSON constraints referenced by the specification. Systems with arbitrary-precision integers or decimals must define whether values outside the interoperable range are rejected or represented as strings under an application schema.

Never silently round, truncate, or coerce a value before verification. A producer and verifier that use different numeric models can produce different canonical bytes from apparently similar input.

## Strings and member names

Preserve Unicode string data as required by the specification; JCS does not introduce Unicode normalization. Visually similar strings can remain distinct. Applications that require normalization must define and apply it as a separate, versioned step before canonicalization.

Reject duplicate member names before signing or verification. Parsers that keep the first value, keep the last value, or expose every duplicate can otherwise disagree about the signed meaning.

## Sorting and serialization

Object properties are serialized in the deterministic order defined by RFC 8785. Arrays retain their original element order. Whitespace is omitted, strings use the required escaping behavior, and numbers use the required serialization.

Use a tested JCS implementation rather than assembling canonical JSON with generic key-sorting and formatting options. Locale-sensitive sorting, recursive map conversions, and incidental runtime serializer behavior are not reliable substitutes.

## Version and algorithm changes

Treat any change to validation, preprocessing, canonicalization, domain separation, or cryptographic algorithms as a protocol change. Publish test vectors and migration rules before accepting a new profile. During a transition, identify the profile explicitly rather than guessing from payload shape.

Do not verify under several profiles and accept whichever succeeds unless the protocol deliberately defines that behavior and analyzes downgrade and ambiguity risks.

## Verification evidence

Maintain positive and negative test vectors covering member ordering, nested objects, arrays, control characters, Unicode edge cases, duplicate names, representative numeric boundaries, malformed input, and altered signatures or digests. Test across every supported implementation language.

Retain the profile specification, implementation versions, test-vector provenance, cross-language results, cryptographic algorithm policy, and migration approvals.

## Failure modes

Common failures include sorting keys without implementing the rest of JCS, accepting duplicate members, canonicalizing after lossy numeric conversion, applying undocumented Unicode normalization, hashing text in a platform-default encoding, and omitting the profile or algorithm identity from the signed context.

## Sources

- [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785)
- [RFC Editor information for RFC 8785](https://www.rfc-editor.org/info/rfc8785)
- [RFC 7493: The I-JSON Message Format](https://www.rfc-editor.org/rfc/rfc7493)
