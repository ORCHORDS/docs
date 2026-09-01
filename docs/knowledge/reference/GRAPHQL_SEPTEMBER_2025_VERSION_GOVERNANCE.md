# GraphQL September 2025 Version Governance

## Purpose

The GraphQL specification defines a type system, query language, validation rules, execution semantics, and introspection system. Implementations often add transport, federation, authorization, and delivery features that are not all part of the core specification.

Governance should identify the exact published specification release used as a baseline and separate core behavior from implementation-specific extensions.

## Current context and source status

The GraphQL specification index lists **September 2025** as the latest published specification and October 2021 as the preceding published release. It also lists a newer dated Working Draft. A Working Draft is development work and must not be described as a published specification release.

GraphQL releases are identified by publication date rather than semantic-version numbers. Compatibility records should therefore use the date and canonical specification URL, not an invented major or minor version.

## Governance pattern

1. Record the exact published GraphQL specification date targeted by each server, gateway, client generator, schema registry, and validation tool.
2. Inventory extensions separately, including federation directives, transport conventions, custom scalars, persisted operations, incremental delivery, and vendor-specific validation rules.
3. Pin client generation and schema tooling to tested versions and retain generated-output diffs during upgrades.
4. Validate schema definition language, executable documents, coercion, null propagation, introspection, and error behavior with representative tests.
5. Treat introspection as schema evidence, not proof of authorization or proof that every field is safe for every caller.
6. Preserve operation names and persisted-operation identifiers unless a controlled migration coordinates all clients and caches.
7. Use Working Draft features only behind an explicit experimental decision, with fallback and promotion criteria.

## Security and resource controls

Specification compatibility does not provide access control. Enforce authorization at field and object boundaries using trusted server-side context. Limit document size, parsing depth, validated complexity, aliases, list expansion, execution time, and response size according to the deployment's threat model.

Do not automatically trust schema descriptions or other rendered text as safe HTML. Restrict any remote schema import or registry integration to approved destinations and credentials.

## Evidence for a baseline change

Retain the old and new baseline dates, affected schema and tool versions, extension inventory, conformance or compatibility test results, generated-code diffs, performance and resource-limit results, known exceptions, and approval. Evidence should state whether a feature comes from the published core specification, a Working Draft, or an external extension.

## Failure modes

- Labeling an API only “GraphQL” hides differences between published baselines and extensions.
- Presenting a Working Draft feature as part of a published release overstates its status.
- Treating federation or a vendor transport convention as core GraphQL creates portability assumptions.
- Using introspection as an authorization decision can expose operations to unintended callers.
- Upgrading schema or code-generation tooling without testing coercion and generated output can break clients.
- Unbounded query complexity can turn valid documents into resource-exhaustion events.

## Sources

- GraphQL specification index: https://spec.graphql.org/
- GraphQL project documentation: https://graphql.org/learn/

Sources were checked on September 1, 2026.

## Scope note

This article governs adoption claims and compatibility evidence for GraphQL specification releases. It does not claim conformance, authorize any operation, or treat federation and vendor extensions as part of the core specification.
