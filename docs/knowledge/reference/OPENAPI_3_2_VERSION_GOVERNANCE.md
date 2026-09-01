# OpenAPI 3.2 Version Governance

## Purpose

The OpenAPI Specification (OAS) defines a language-agnostic description format for HTTP APIs. The latest published OpenAPI Specification is **3.2.0**, dated September 19, 2025.

API descriptions, generators, validators, and documentation tooling should record the exact OAS version they target so feature compatibility and parser behavior are explicit.

## Version semantics

OAS uses a `major.minor.patch` versioning scheme.

The `major.minor` portion identifies the feature set. Patch releases are for corrections and clarifications rather than feature-set changes. Tooling that supports a given feature set, such as 3.1, should generally support all 3.1.x patch versions.

The specification also notes that minor releases can occasionally contain non-backwards-compatible changes where the benefit is judged to outweigh the impact. Consumers should therefore test a new minor version rather than assuming feature-set upgrades are risk-free.

## Governance pattern

1. Store the exact `openapi` version declared by every published API description.
2. Pin generators, linters, validators, and documentation tooling to versions known to support the target OAS feature set.
3. Treat a 3.1-to-3.2 migration as a feature-set migration, not only a patch update.
4. Preserve the previous description and generated artifacts when changing major/minor OAS versions so compatibility changes can be reviewed.
5. Test external references, schema behavior, HTTP methods, callbacks/webhooks, and code-generation paths after migration.
6. Record any tooling limitation that requires using an older OAS version even when a newer specification exists.
7. Do not treat informational JSON schemas as more authoritative than the specification text when they differ.

## External references

OpenAPI descriptions can contain references to external resources that tooling may dereference automatically. Those resources can be hosted on untrusted domains.

Consumers should apply network allowlists, size limits, cycle detection, timeout limits, and controlled authentication behavior before dereferencing remote descriptions or schemas.

## Markdown and HTML

Some OpenAPI fields permit Markdown that can contain HTML. The OAS states that tooling is responsible for appropriate sanitization. Renderers should therefore treat documentation text as untrusted content rather than injecting it directly into privileged HTML contexts.

## YAML and JSON handling

OpenAPI descriptions can be represented in JSON or YAML. YAML 1.2 is the recommended YAML version because of its alignment with JSON semantics. Tooling should use parsers configured consistently and avoid implicit conversions that change API-description values unexpectedly.

## Failure modes

- Calling an API document merely “OpenAPI 3” hides meaningful 3.0/3.1/3.2 feature differences.
- Assuming every 3.1-capable tool supports 3.2 can break generation or validation pipelines.
- Auto-fetching arbitrary external references creates network and resource-exhaustion risks.
- Rendering unsanitized Markdown/HTML can introduce active-content vulnerabilities.
- Treating a patch release as a new feature set misunderstands OAS version semantics.

## Sources

- OpenAPI Specification v3.2.0: https://spec.openapis.org/oas/v3.2.0.html
- OpenAPI latest published specification: https://spec.openapis.org/oas/latest.html

## Scope note

This article describes version and tooling governance for OpenAPI descriptions. It does not claim API conformance, correctness, or compatibility with a particular generator or gateway.