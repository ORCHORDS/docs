# CBOR RFC 8949 Version Governance

## Purpose

Concise Binary Object Representation (CBOR) is a compact binary data format. Interoperability depends not only on successful parsing but also on data-model choices, tag semantics, deterministic encoding requirements, and application profiles.

Producers and consumers should identify RFC 8949 as their baseline where applicable and document any companion standards or application profiles they require.

## Current context and source status

**RFC 8949**, published in December 2020, is the Internet Standard for CBOR and obsoletes RFC 7049. RFC 7049 is therefore a legacy reference, even though many documents produced under it remain parseable.

Companion specifications address separate concerns. For example, RFC 8742 defines CBOR sequences. A claim of RFC 8949 support does not by itself imply support for sequences, every registered tag, deterministic encoding, a particular schema language, or an application protocol.

## Governance pattern

1. Record the governing RFC, media type, application profile, tag set, and any structural schema used by each interface.
2. Pin encoders and decoders to tested versions and document configuration that changes accepted or emitted representations.
3. Define whether preferred serialization or deterministic encoding is required. If signatures or hashes cover encoded bytes, specify and test the exact deterministic rules.
4. Maintain an allowlist or explicit handling policy for tags used by the application. Registration of a tag does not prove that every decoder implements its semantics.
5. Set limits for nesting, collection lengths, byte and text strings, integers, decompressed or expanded output, and total decoding work.
6. Test duplicate map keys, invalid UTF-8, indefinite-length items, non-preferred encodings, unknown tags, trailing data, and numeric boundary cases according to the profile.
7. Treat RFC 7049-era inputs as a documented compatibility mode rather than silently claiming that all legacy behavior is RFC 8949 behavior.

## Transport and sequences

Use the registered media type appropriate to the payload and protocol. Do not infer that a byte stream contains one CBOR data item, a CBOR sequence, or a framed application message without an explicit contract. When profiles or content-type parameters are used, preserve them in interface and test evidence.

## Determinism and signatures

Equivalent CBOR data models can have different byte encodings. Signature verification, content addressing, and reproducible hashing therefore require an agreed deterministic encoding profile; ordinary decode-and-reencode behavior is not sufficient evidence. Verify canonicalization before signing and reject representations outside the profile where the protocol requires that behavior.

## Failure modes

- Referring only to “CBOR” hides whether RFC 8949, legacy RFC 7049 behavior, sequences, or an application profile is intended.
- Assuming every decoder implements all registered tags creates semantic mismatches.
- Signing arbitrary encoder output without deterministic rules makes signatures non-portable.
- Accepting unbounded nesting or lengths exposes decoders to resource exhaustion.
- Treating a parseable legacy representation as proof of current-profile conformance overstates compatibility.
- Conflating CBOR with other binary formats obscures different data models and extension mechanisms.

## Sources

- RFC 8949, Concise Binary Object Representation: https://www.rfc-editor.org/rfc/rfc8949.html
- IANA CBOR tags registry: https://www.iana.org/assignments/cbor-tags/cbor-tags.xhtml
- RFC 8742, Concise Binary Object Representation Sequences: https://www.rfc-editor.org/rfc/rfc8742.html

Sources were checked on September 1, 2026.

## Scope note

This article governs CBOR baseline, profile, and compatibility decisions. It does not claim that an encoder or decoder conforms, that a tag set is universally canonical, or that RFC 8949 alone defines an application's data model.
