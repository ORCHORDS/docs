# Event Driven Schema Registry Evolution

## Scope

This article addresses the engineering discipline of evolving event schemas in an event-driven architecture. It explains why a schema registry is necessary, what compatibility guarantees the registry enforces, and how the producer, the broker, and the consumer each participate in the evolution. The discussion covers Avro, Protobuf, and JSON Schema as registry-supported formats, the differences between backward, forward, and full compatibility, and the operational practices that keep a schema-bearing system healthy over years. The article applies to any event-driven system: Kafka with Confluent Schema Registry, EventBridge, Pub/Sub, Kinesis, and Cloudflare Queues with Workers binding JSON validators.

## Workflow or implementation guidance

A schema registry is a service that stores the canonical version of every event schema and answers two questions: "is this schema compatible with the previous one?" and "what is the current schema for this topic or stream?". Without a registry, schema drift is inevitable: producers add fields, consumers ignore fields, and the implicit contract between them erodes until an event arrives that no consumer can parse.

The first step in adoption is to choose the wire format. Avro is the historical default and is well supported by Confluent Schema Registry. Protobuf is increasingly common because of its cross-language tooling and its compact encoding. JSON Schema is the format of choice for HTTP and webhook systems, where the schema registry takes the form of a stored JSON Schema document or a Stoplight Elements workspace. The choice of format dictates the registry's compatibility machinery: Avro and Protobuf have well-defined rules for backward and forward compatibility; JSON Schema does not have universally agreed rules, but compatibility can be enforced at the application layer by diffing schemas and applying project-defined rules.

The second step is to register every topic's schema at the producer side and to enforce that producers cannot publish without a registered schema. The producer obtains the schema ID at build time (or fetches it from the registry), embeds the ID in the message header, and serialises the payload against the registered schema. The third step is to enforce validation at the consumer side. The consumer reads the schema ID from the message, fetches the schema from the registry, deserialises, and validates. This indirection is what allows the schema to evolve without consumer recompilation.

The fourth step is to choose the compatibility mode. Backward compatibility means a consumer using the new schema can read data produced with the old schema; this allows consumers to roll forward without coordinating with producers. Forward compatibility means a consumer using the old schema can read data produced with the new schema; this allows producers to roll forward without coordinating with consumers. Full compatibility means both. Backward compatibility is the safe default because new fields can be added freely; consumers that do not know about the new field simply ignore it. Removing a field is a breaking change under backward compatibility and requires careful coordination.

The fifth step is to plan for breaking changes. Some changes cannot be made backward-compatibly: renaming a field, changing a field's type, removing a required field. For these, the convention is to version the topic (e.g., `orders.v1`, `orders.v2`) and run both topics in parallel during a migration window. The consumer subscribes to both, processes events from each, and is decommissioned only after the producer has fully cut over. This is the pattern that lets an event-driven system evolve over years without big-bang migrations.

## Controls

Schema-registry controls fall into three categories: producer-side validation, consumer-side validation, and CI-side policy. Producer-side validation is enforced by the registry refusing to register an incompatible schema. CI-side policy is enforced by a build check that runs the producer's schema diff against the registered version and fails the build on a breaking change. Consumer-side validation is enforced by the consumer code refusing to deserialise an event that does not conform to the expected schema; this is the last line of defence.

Operational controls include: schema deprecation policies (a schema version is marked deprecated and removed after a documented window); registry availability (the registry is a critical path for producers and consumers and must be highly available); and schema documentation (every schema carries a description, an owner, and a link to the contract documentation). Without documentation, the schema is technically valid but practically opaque.

## Validation evidence

Validation must prove that the compatibility rules are enforced. A simple test adds a new optional field and verifies that the registry accepts the change. A more demanding test removes a field and verifies that the registry rejects the change under backward compatibility. A yet more demanding test simulates a producer using a newer schema and a consumer using an older schema and verifies that the consumer can still read the data.

Validation must also prove that the migration path works. The v1-to-v2 migration is run in staging: a producer publishes to both v1 and v2, a consumer reads both, and the test asserts that every v1 event is processed correctly by the v2-aware consumer and vice versa. Only after this is rehearsed is the production cutover attempted.

## Failure modes and correction

The dominant failure is the registry being optional. Producers "register when convenient" and bypass it the rest of the time. The schema drift is invisible until a consumer breaks. The cure is to make the registry a hard dependency: the producer's deploy pipeline fails if the schema is not registered, and the consumer's deserialiser fails if the schema is not in the registry. A second failure is the wrong compatibility mode being chosen. Backward compatibility is assumed, but the producer removes a field, and old consumers break. The cure is to state the compatibility mode explicitly in the schema registry's policy and to fail the build on a violation.

A third failure is the schema registry being a single point of failure. The registry is unavailable, producers cannot publish, and the system halts. The cure is to run the registry as a highly available service with read replicas and to cache schema lookups on the consumer side. A fourth failure is documentation drift. The schema is correct but the documentation that explains what the fields mean is out of date. The cure is to require a description on every schema field and to fail the build on missing descriptions.

A fifth failure is the topic-versioning pattern being applied incorrectly. The producer publishes to v2 before the consumer is ready, and v1 events are lost because no consumer is subscribed. The cure is to keep v1 alive until every consumer has cut over, and to decommission v1 only after a documented draining window.

## Limitations

The schema registry adds operational surface area: another service to run, another dependency to monitor, another compatibility policy to maintain. The pattern also assumes that the producer and the consumer share a registry; in a multi-cloud or cross-organisation event bus, the registry is federated, and the compatibility guarantees depend on the federation being correctly configured. The pattern does not solve semantic compatibility: a field can be schema-compatible (same name, same type) and semantically broken (the meaning of "price" changed from cents to dollars). The cure for semantic compatibility is documentation, code review, and contract tests—not the registry.

## Canonical sources

- Confluent — *Schema Registry documentation*, including the fundamentals of compatibility and evolution: https://docs.confluent.io/platform/current/schema-registry/index.html
- Confluent — *Schema Evolution and Compatibility* page, defining backward, forward, and full compatibility: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
- Apache Avro specification — the format underlying Confluent Schema Registry's canonical compatibility model
- Martin Fowler — *Patterns of Enterprise Application Architecture*, on the role of schema and contract in long-lived integrations
