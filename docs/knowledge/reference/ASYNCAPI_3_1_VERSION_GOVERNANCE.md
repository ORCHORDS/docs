# AsyncAPI 3.1 Version Governance

## Purpose

AsyncAPI describes event-driven and message-based APIs. An AsyncAPI document connects channels, operations, messages, servers, protocol bindings, and reusable components, so its specification version affects more than presentation.

Organizations should record the exact specification version used by each description and verify that every producer, validator, generator, and renderer supports that version.

## Current context and source status

The AsyncAPI specification repository identifies **3.1.0** as a released specification. Its release history lists 3.0.0 as the preceding 3.x release. These are published project specifications, not IETF RFCs or W3C Recommendations.

Version 3 introduced a model centered on channels and operations. A migration from 2.x therefore requires a model review rather than a mechanical field rename.

## Governance pattern

1. Preserve the document's exact `asyncapi` value in source control and generated evidence.
2. Pin parsers, validators, generators, renderers, and diff tools to releases with demonstrated support for that specification version.
3. Inventory protocol bindings separately. Support for the core document does not prove support for every Kafka, AMQP, MQTT, WebSocket, or other binding in use.
4. During a 2.x-to-3.x migration, map channels, operations, messages, replies, traits, and reusable references explicitly.
5. Test server variables, security schemes, correlation identifiers, message headers, and payload schemas after migration.
6. Preserve stable identifiers where consumers use them for generated code, documentation links, policy checks, or change detection.
7. Record tool limitations and any approved decision to remain on an earlier specification release.

## Untrusted content and references

Descriptions can include human-readable content and references processed by automated tooling. Render Markdown or HTML as untrusted input. Before resolving remote references, enforce approved schemes and destinations, response-size and redirect limits, timeouts, and cycle detection. Do not forward ambient credentials to a referenced location.

## Compatibility evidence

A migration record should identify the old and new specification versions, affected bindings and tools, validation results, representative generated artifacts, compatibility tests, exceptions, and the approver. Retain the previous description long enough to make semantic changes reviewable.

## Failure modes

- Calling a document only “AsyncAPI 3” conceals minor-version and tooling differences.
- Assuming 2.x tooling understands the 3.x channel and operation model can produce incomplete artifacts.
- Treating core-specification support as proof that every protocol binding is supported creates runtime mismatches.
- Automatically resolving unrestricted external references creates network and resource-exhaustion risks.
- Rendering description text without sanitization can introduce active content.
- Changing identifiers during migration can create noisy or breaking generated-code changes unrelated to API behavior.

## Sources

- AsyncAPI specification repository: https://github.com/asyncapi/spec
- AsyncAPI specification releases: https://github.com/asyncapi/spec/releases
- AsyncAPI documentation: https://www.asyncapi.com/docs

Sources were checked on September 1, 2026.

## Scope note

This article governs specification-version adoption for AsyncAPI descriptions. It does not claim that a description is correct, that an implementation conforms, or that a particular broker, binding, or code generator is compatible.
