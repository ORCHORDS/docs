# IETF RFC 9562 — Universally Unique IDentifiers (UUIDs), v7

## Purpose

Establish governance on the IETF RFC 9562 definition of UUIDs and, particularly, the UUID version 7 (UUIDv7) variant. RFC 9562 is the primary-source reference for any program that generates, parses, or stores UUIDs in modern distributed systems, with a focus on UUIDv7's time-orderable properties.

## Current status

- RFC 9562 published by the IETF in May 2024 under the IETF Stream. It is the canonical current UUID specification; it formalizes several versions and consolidates prior definitions (RFC 4122's v1/v3/v4/v5 are still syntactically valid in the updated grammar, with semantic clarifications).
- RFC 9562 defines UUIDv1, UUIDv3, UUIDv4, UUIDv5, UUIDv6, UUIDv7, UUIDv8. UUIDv7 is the most significant new addition for engineering adoption: a time-ordered UUID that combines millisecond Unix-epoch-ordered timestamp bits with the random portion of v4.
- Status as of 2026-09-04: current and authoritative. No subsequent IETF document supersedes RFC 9562 for the UUID grammar defined therein.

## Sources

- Primary: IETF RFC 9562, "Universally Unique IDentifiers (UUIDs)," https://www.rfc-editor.org/rfc/rfc9562 — and the IETF datatracker entry https://datatracker.ietf.org/doc/rfc9562/ .
- Companion / historical: RFC 4122 ("A Universally Unique IDentifier (UUID) URN Namespace," July 2005) which RFC 9562 obsoletes for newly generated UUID grammar — though RFC 4122 URN namespaces (`uuid:NAMESPACE:DNS`, `uuid:NAMESPACE:URL`, `uuid:NAMESPACE:OID`, `uuid:NAMESPACE:X500`) are still in use for v3/v5 inputs.
- Authoritative references cited in RFC 9562: RFC 4647 (BCP 47 language subtag matching), ISO/IEC 11578:1996 (UUID procedures), RFC 4122 itself, RFC 3339 (timestamps), IETF draft-pedersen-uuid-bis.

## Scope note

UUIDs in RFC 9562 are 128-bit identifiers with a specific binary layout. The grammar (fields, byte order, variant bits) is normative and must be followed by any adopted implementation. Governance-relevant elements of the specification:

1. UUID layout. A UUID is `xxxxxxxx-xxxx-Mxxx-Nxxx-xxxxxxxxxxxx` where M is the version field (4 bits indicating one of v1/v3/v4/v5/v6/v7/v8) and N is the variant field (`10x` for RFC 4122/9562 legacy). The variant field distinguishes RFC 9562 / 4122 UUIDs from other UUID variants (e.g., Microsoft's early variants).
2. Version field semantics. The version determines how the remaining bits are interpreted:
   - v1: Gregorian time + clock sequence + node (MAC). Time-ordered but reveals host info.
   - v3 / v5: MD5 / SHA-1 hash of a namespace + name. Deterministic given inputs.
   - v4: 122 random bits + version/variant. Most common today but not time-ordered.
   - v6: Reordered-time variant of v1 (preserves node/clock fields, sorts first by time).
   - v7: 48 bits of millisecond Unix-epoch timestamp + 12 bits of sub-millisecond precision (or random) + 62 bits of random data. Time-ordered and sortable; the standard recommendation when a sortable UUID is acceptable.
   - v8: "Custom" UUID; user-defined content within the format. New in RFC 9562.
3. UUIDv7 governance properties. UUIDv7 is the recommendation when (a) a temporal ordering of identifiers is needed (creation-order sort correlates with insertion order in B-tree indexes), or (b) log lines, event records, or document versions need to be naturally sortable without an additional timestamp column. UUIDv7 trades exposing millisecond creation time for the sortability property — engineering teams should make this trade-off explicit in their governance records.
4. None-collision expectations. UUIDv7 inherits v4's collision resistance from the random portion (62 bits) but combines it with a 48-bit timestamp field, so two UUIDs created in the same millisecond by the same process still have ~5.8 × 10^18 distinct values to draw from in the random portion.
5. Inter-version conversion caveats. Converting a v1 UUID to v6 is defined; converting between v1/v6 and v7 is not because the timestamp precision and node fields differ. Adoption plans that import legacy v1 UUIDs must not promise a one-to-one semantic conversion to v7.
6. URN namespace. UUIDs are also valid URNs (`urn:uuid:...`). RFC 9562 retains the namespace layout (`urn:uuid:NAMESPACE:value`) for v3/v5 hashing inputs.

This article is scoped to the UUID grammar and version semantics defined in RFC 9562. It does not cover canonicalization of UUID strings (case, dash placement) beyond what RFC 9562 prescribes, nor does it cover non-IETF ID formats such as ULID, NanoID, KSUID — those are separate references. RFC 4122 is preserved as a historical companion but RFC 9562 supersedes the active document.
