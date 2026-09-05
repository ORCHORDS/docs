---
title: "JSON Version Governance (RFC 8259, December 2017)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 8259 (December 2017); https://www.rfc-editor.org/rfc/rfc8259"
---

# JSON Version Governance (RFC 8259, December 2017)

## Scope

Reference card for JavaScript Object Notation (JSON) as specified in IETF RFC 8259 (December 2017). Used by API, interchange-format, configuration, and telemetry teams when documenting wire-level JSON usage, grammar constraints, and interoperability expectations. Treats RFC 8259 as the current authoritative specification that supersedes RFC 7159.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 8259, "The JavaScript Object Notation (JSON) Data Interchange Format" |
| Status | Internet Standard (STD 90) |
| Obsoletes | RFC 7159 |
| Predecessor | RFC 4627 (informational) |
| Encoding | UTF-8, UTF-16, or UTF-32; UTF-8 strongly recommended |
| Grammar | Objects, arrays, strings, numbers, true, false, null |
| Number range | Arbitrary precision; implementation-defined limits |
| Interoperability | Reject non-conformant input per section 4; do not silently accept non-JSON extensions |
| Verification source | https://www.rfc-editor.org/rfc/rfc8259 |

## Plan

1. Identify the deployment context (API request and response bodies, configuration files, telemetry, build manifests).
2. Map required features against RFC 8259 (grammar, encoding, interoperability behavior).
3. Capture the operational requirements: parser selection, max depth, max string length, number precision, duplicate-key handling.
4. Validate against a current strict JSON parser and your interchange policy.

## Inputs

- Wire-format requirement (UTF-8, UTF-16, or UTF-32 BOM tolerance).
- Parser configuration (max depth, max string length, max number magnitude, duplicate-key handling).
- Document size limit (recommended: enforce per-message).
- Error reporting policy (RFC 8259 section 4 conformance detection).

## ORCHORDS Profile

This guide is used as a reference when reviewing JSON interchange documentation or designing parser policy. It does NOT introduce parser behavior beyond what RFC 8259 specifies. When an interchange requires a behavioral rule that is not captured here, escalate to a fresh review against the current RFC.

## Implementation Notes

- Use a strict parser that enforces RFC 8259 conformance and rejects trailing characters per section 4.
- The interchange profile recommends UTF-8 unless interoperability with a legacy partner requires otherwise.
- JSON numbers are decimal and have no explicit precision; do not depend on IEEE 754 rounding across language boundaries without explicit handling.
- Duplicate object member names have unspecified behavior; strict parsers must reject them, lenient parsers should be documented.
- For canonical or signed JSON, use RFC 8785 (JSON Canonicalization Scheme) rather than ad-hoc sorting.
- Use JSON Schema (RFC draft or 2020-12) for inter-service validation; do not conflate with the interchange format.

## Companion Documents

- RFC 8259 (current JSON grammar)
- RFC 8785 (JSON Canonicalization Scheme)
- JSON Schema 2020-12 (validation language)
- RFC 8949 (CBOR — binary alternative)
- RFC 7464 (JSON Text Sequences — streaming variant)
