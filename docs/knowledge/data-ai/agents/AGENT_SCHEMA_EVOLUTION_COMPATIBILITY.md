# Schema Evolution for Agent Messages and Tool Contracts

## Scope

Agent systems exchange task envelopes, tool arguments, results, events, and persisted checkpoints over long periods. A producer and consumer may deploy at different times, so an apparently harmless field change can corrupt behavior or strand active runs. This article defines compatibility discipline for structured contracts. It does not address protocol-level version negotiation already documented for A2A or MCP; it concerns application schemas layered on those transports.

JSON Schema 2020-12 defines validation vocabularies and identifiers, while Protocol Buffers documents concrete compatibility practices for its wire format. HTTP semantics explains representation evolution through media types and negotiation. No single source makes all application changes safe; compatibility depends on producer, consumer, storage, and business semantics.

## Workflow

1. Give each contract a stable identifier, schema language and dialect, owner, semantic purpose, and compatibility policy.
2. Inventory active producers, consumers, persisted records, queues, and replay windows before proposing a change.
3. Classify the change as backward compatible, forward compatible, both, or breaking for each actual consumer. Adding an optional field is not safe if a consumer rejects unknown properties or interprets absence differently.
4. For compatible additions, define default semantics for older data and require new consumers to tolerate documented unknown fields. Do not reuse removed names or numeric tags.
5. For breaking changes, introduce a new contract identifier or major representation version. Support translation at a controlled boundary rather than scattering guesses throughout consumers.
6. Deploy readers before writers when readers must understand new output. For removal, stop writing, wait through retention and in-flight windows, migrate durable data, then remove reading support.
7. Validate at ingress and egress. Store the contract identifier with durable payloads so replay does not depend on the current default.
8. Retire a version only after measured traffic, queue depth, persisted inventory, and rollback requirements show it is no longer needed.

## Controls, data, and evidence

Maintain a registry containing canonical schemas, ownership, status, compatibility mode, migration adapters, and supported lifecycle dates. Pin JSON Schema dialects and resolve `$id` and references from approved locations. Apply limits to recursion, string size, collection count, and numeric range; schema-valid does not mean operationally safe.

For each message record contract ID, producer revision, validation result, adapter chain, consumer revision, and rejection category. Preserve digests rather than sensitive full payloads where sufficient. Evidence includes compatibility review, golden fixtures, consumer-driven tests, migration counts, unknown-field tests, rollback drills, and proof that retired identifiers are rejected or intentionally archived.

## Validation tests

Run old readers against new writer fixtures and new readers against old fixtures. Test absent fields, explicit null, unknown enum values, unknown properties, reordered members, minimum and maximum numbers, and Unicode edge cases. For binary formats, verify tags are never reused and changing a field type follows the format's official compatibility rules.

Replay a persisted pre-migration checkpoint through the current adapter. Roll back a writer after readers deploy and confirm compatibility. Place both versions in the same queue and verify dispatch uses the embedded identifier. Fuzz references and deeply nested schemas to enforce parser limits. Intentionally remove an adapter while old records remain; retirement gates must block deployment. Verify semantic invariants, not only validator success—for example, a new default must not broaden action scope.

## Failure handling

Unknown contract identifiers go to quarantine or a dead-letter path with bounded retention; they are not handed to the model for interpretation. Validation failure stops dependent side effects and returns a stable contract error. If a writer emits invalid data, disable that writer revision and preserve representative digests and metadata.

If migration is only partly complete, keep old readers and make migration idempotent. Never mark a record migrated before the transformed record and migration marker commit atomically. On semantic incompatibility discovered after release, stop new production, route affected versions through a reviewed adapter if possible, and reassess already processed actions. Avoid rewriting historical evidence merely to match the newest schema.

## Limitations

Syntactic validation cannot establish semantic compatibility. JSON number handling differs across languages, and unknown-field preservation varies by serializer. Bidirectional adapters can lose information. Supporting many versions increases attack surface and operational burden. Long-lived offline clients can extend retirement indefinitely unless policy sets a boundary. Schema governance also cannot prevent a consumer from ignoring validated fields or applying unsafe defaults.

## Canonical sources

- **JSON Schema, Draft 2020-12 Specification:** https://json-schema.org/draft/2020-12/json-schema-core
- **JSON Schema, Draft 2020-12 Validation:** https://json-schema.org/draft/2020-12/json-schema-validation
- **Protocol Buffers, Updating a Message Type:** https://protobuf.dev/programming-guides/proto3/#updating
- **IETF, HTTP Semantics (RFC 9110):** https://www.rfc-editor.org/rfc/rfc9110.html
