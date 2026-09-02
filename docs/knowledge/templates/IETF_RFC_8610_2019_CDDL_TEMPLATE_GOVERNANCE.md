# IETF RFC 8610:2019 CDDL Template Governance

## Purpose

IETF RFC 8610, "Concise Data Definition Language (CDDL): A Notational Convention to Express Concise Binary Object Representation (CBOR) and JSON Data Structures," defines a notational convention for expressing CBOR and JSON data structures. CDDL provides a compact, human-readable notation for defining the structure of CBOR data items and JSON values, used for protocol data definitions, schema validation, and code generation. This article governs the application of RFC 8610 as a template for designing data schemas for CBOR and JSON exchanges.

## Scope

The specification applies to any organization that defines CBOR or JSON data structures for protocols, APIs, or storage. Within this knowledge base, the article covers CDDL types (any, bool, uint, nint, float, float16, float32, float64, byte string, text string, array, map, tagged data items), the type composition rules (group, choice, optional, tagged), and the use of CDDL in the design process. It does not cover the CBOR data format itself (RFC 8949); CDDL is a notational convention for describing CBOR or JSON structures.

## Workflow

1. Identify the data structures to be defined for the CBOR or JSON exchange.
2. Express each structure in CDDL using the type composition rules. Start with the root type and decompose it into its component types.
3. Apply CDDL features as needed:
   - Group: a name for a reusable set of structures.
   - Choice: a type that may be one of several alternatives.
   - Optional: a key that may or may not be present in a map.
   - Tagged data items: use the IANA-registered CBOR tag to express semantic meaning beyond the bare type.
4. Validate the CDDL against the CDDL specification's grammar and against any test vectors.
5. Use the CDDL with code generators to produce CBOR / JSON encoders and decoders, or with schema validators at the protocol boundary.
6. Document the CDDL schema as part of the protocol's public specification.

## Controls and evidence

Schema evidence includes the CDDL definition, the validation test vectors, the generated code (where generated from the CDDL), and the schema validation records at runtime. Each CDDL definition should be published with the protocol and maintained as the protocol evolves.

## Validation

Validation should confirm the CDDL grammar is valid, the CDDL expresses the intended data structure (test vectors should encode and decode successfully), the schema validation at runtime operates, and the CDDL is maintained as the protocol evolves. Sample testing across protocol messages confirms the CDDL's accuracy.

## Failure correction

Common failure modes: CDDL is written without reuse in mind and produces duplicated structures (corrective: introduce groups for reusable structure); CDDL is not validated against test vectors (corrective: produce test vectors for each structure and validate the CDDL against them); schema validation at runtime is missing or permissive (corrective: enforce schema validation at the protocol boundary); CDDL is not maintained (corrective: maintain the CDDL alongside the protocol and update on changes).

## Limitations

RFC 8610 is a notational convention; it does not certify any specific implementation. CDDL is not a programming language; it is a schema language for CBOR and JSON. CDDL does not address the semantics of the data items beyond the type composition; the semantics must be documented separately.

## Scope note

This article summarizes project-neutral use of IETF RFC 8610 as a template. It does not assert any specific protocol's conformance or claim any interoperability outcome.

## Canonical sources

- IETF RFC 8610 — Concise Data Definition Language (CDDL): https://www.rfc-editor.org/rfc/rfc8610
- IETF RFC 8949 — Concise Binary Object Representation (CBOR): https://www.rfc-editor.org/rfc/rfc8949