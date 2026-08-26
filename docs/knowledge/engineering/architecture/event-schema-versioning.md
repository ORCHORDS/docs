# event-schema-versioning

**Issue:** An event-driven system has dozens of producers and consumers sharing event streams, and then someone needs to change an event. A field is added without a default and old consumers crash on decode; a field is renamed and half the downstream analytics silently nulls out; two teams ship incompatible versions the same week and the schema registry rejects a deploy mid-rollout. Events are immutable once published — unlike REST contracts you cannot patch history — so every schema change has to coexist with months or years of old messages still being replayed. Confluent's documentation and the surrounding ecosystem (Conduktor, Solace guidance) converge on the same answer: enforce explicit compatibility semantics at registration time and follow disciplined evolution rules. Without that, schema evolution becomes an uncoordinated production incident generator.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Principles

1. **Compatibility is a contract between reader and writer versions.** BACKWARD: consumers using the new schema can read data produced with the last schema (delete a field or add an optional one). FORWARD: old consumers read new data (add an optional field or delete one). FULL: both directions. Transitive variants check against all previous versions, not just the latest — the only safe setting for long-lived replayable streams.
2. **Events are immutable; schemas must evolve in place.** You cannot rewrite a year of Kafka history. Every schema version ever produced may be replayed by a new consumer, a backfill, or a disaster recovery, so evolution strategy has to assume permanent coexistence of versions.
3. **Prefer backward compatibility as the default posture.** Confluent's best-practices guidance recommends backward as the default level because consumers are typically harder to coordinate than producers: deploy new consumers first, then producers can ship at will.
4. **Additive-only evolution is the discipline that makes it work.** Add fields with defaults, never rename, never remove in place, never change a field's type. Every breaking change short-circuits the registry and forces a new topic/stream or a coordinated migration.
5. **The registry is a governance gate, not a library.** A schema registry exists to enforce compatibility rules at registration time so breaking changes "never reach production." Treat registration as part of CI/CD, not a manual console step.
6. **Version belongs in the envelope.** Consumers must be able to determine the schema of any message without guessing: schema-id in the wire format (registry-serialized payloads) or an explicit version field in the event envelope.

## Implementation Approaches

1. **Registry-gated CI/CD.** Validate every proposed schema against the registry's compatibility mode as a pipeline step before the producer deploy proceeds; a rejected schema fails the build, not the broker. Pin per-subject compatibility (BACKWARD_TRANSITIVE by default) as code.
2. **Add-with-defaults for optional data.** New fields get sensible defaults (null for nullable, sentinel for enums-with-fallback) so old readers and new readers both decode every historical message. Document that consumers must tolerate unknown fields (Avro/Protobuf do this natively; JSON Schema consumers need explicit ignore-unknown handling).
3. **Deprecate-then-remove across a horizon.** Mark the field deprecated, wait out a defined retention-and-replay horizon (all replay tooling upgraded), then remove in a release that is BACKWARD-compatible relative to the versions still in storage. The horizon is a documented number, not vibes.
4. **Upcasting at the consumer boundary.** When a consumer must handle v1 and v2, normalize early: a thin upcast layer translates every inbound event to the latest internal model so business logic sees one shape. Keep upcasters versioned alongside schema history.
5. **New event type for semantic breaks.** When meaning changes (OrderCancelled now means "requested" not "completed"), publish a new event type (OrderCancelRequested) and stop producing the old one rather than overloading the original's schema.
6. **Consumer-driven contract tests.** Run producers' sample events against consumers' deserializers in CI (schema-compatibility plus semantic assertions). Compatibility modes catch structural breaks; only contract tests catch "the field exists but means something different now."
7. **Schema documentation as metadata.** Register field docs, owners, and change history with the schema so downstream teams can assess impact before consuming a new version.

## Gotchas and Failure Modes

1. **Backward-only checks miss the replay window.** BACKWARD validates against the latest version only; an old-but-still-replayable v3 message can still break a consumer registered after v9. Use transitive modes on any stream that gets replayed or retained.
2. **Defaults that are wrong are worse than no defaults.** A default of 0 or empty-string flows into business logic as legitimate data. Prefer nullable defaults plus explicit "field absent" handling, and forbid magic sentinel values in the style guide.
3. **Renaming is indistinguishable from delete-plus-add.** Registry tooling sees an additive change plus a removal; if the removal slips into the same registration, old readers drop the data. Renames must go through the deprecate-then-remove path with dual-field publication.
4. **Enum evolution is quietly breaking.** Adding an enum value is FORWARD-breaking: old consumers fail or mis-route on the unseen value. Consumers must define an unknown-enum fallback, or producers must gate new values on consumer capability.
5. **Two registries, one truth.** Multi-region or multi-team deployments that drift registry state accept schemas the other environment would reject. Replicate registry metadata with the same rigor as data, and validate against the strictest environment.
6. **Unregistered escape hatch abuse.** Raw JSON events that skip the registry grow into the majority of traffic because they're easy; then evolution is unenforceable. Block unserialized topics by policy and audit periodically.

## When (Not) To Apply

1. **Apply on every long-lived, multi-consumer stream.** Analytics pipelines, audit feeds, and integration events with replay requirements are exactly where registration gates and transitive compatibility pay for themselves.
2. **Apply in organizations with many consuming teams.** The registry's value scales with the number of teams you cannot coordinate synchronously; it is the coordination mechanism.
3. **Lighten up for internal, short-lived, single-consumer streams.** A transient queue between two services you own, with no replay and lockstep deploys, may only need a shared types module and contract tests — full registry infrastructure is overhead.
4. **Do not version around a wrong abstraction.** If a schema needs its third breaking change in a quarter, the event boundary is wrong; spend the effort redesigning the event type instead of mastering its versioning.
