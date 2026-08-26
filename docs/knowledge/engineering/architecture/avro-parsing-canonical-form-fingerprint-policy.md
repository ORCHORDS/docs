# Avro parsing canonical form fingerprint policy

**Issue:** Hashing the original Avro schema text makes whitespace, key order, aliases, documentation, and other non-parsing changes look like incompatible schemas. Conversely, treating a short fingerprint as proof of authenticity turns a compact identifier into a security control it was not designed to be.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Derive identity from Avro Parsing Canonical Form when the goal is equivalence of parsing behavior.
- Store the original schema and its canonical form alongside the fingerprint so collisions and tooling disagreements can be investigated.
- Use a collision-resistant digest such as SHA-256 for governance or untrusted, high-cardinality registries; document any shorter fingerprint and its collision budget.
- Keep compatibility policy separate from identity: run reader/writer compatibility checks even when a new fingerprint is produced.
- Sign the registry record or release manifest when provenance matters; a fingerprint alone is not an authenticity proof.
- Pin the Avro specification and library versions used by canonicalization tooling.

## Implementation and tests

Canonicalize with a tested Avro implementation, then fingerprint the exact canonical bytes. Register the tuple of original schema, canonical form, digest algorithm, digest, subject, version, and compatibility result atomically. Reject a digest lookup when the stored canonical bytes do not match.

Use golden tests for namespace qualification, primitive simplification, object-key ordering, escaped strings, integer normalization, and removal of attributes that do not affect parsing. Cross-check the canonical output with a second implementation before a registry migration.

## Gotchas and applicability

Parsing Canonical Form deliberately removes fields that do not change parsing, including information applications may still care about operationally. Equal canonical forms do not mean equal documentation, defaults policy, business meaning, or release approval. Different canonical forms do not automatically prove incompatibility.

Algorithm labels are part of the identifier. Never compare a truncated or unlabeled digest as though it were a globally unique schema key.

## Official sources

- [Apache Avro specification: Parsing Canonical Form for Schemas](https://avro.apache.org/docs/current/specification/#parsing-canonical-form-for-schemas)
- [Apache Avro specification: Schema Fingerprints](https://avro.apache.org/docs/current/specification/#schema-fingerprints)
