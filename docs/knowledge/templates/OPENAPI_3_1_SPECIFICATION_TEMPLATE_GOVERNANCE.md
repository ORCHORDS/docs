# OpenAPI 3.1 Specification Template Governance

## Purpose
Establish the governance pattern for templating OpenAPI 3.1 specifications for every HTTP API produced or consumed by the studio, including structure, naming, versioning, and security requirements.

## Scope
Applies to every HTTP API produced by the studio and to every external HTTP API consumed by the studio whose specification is reviewed or maintained.

## Workflow
1. Use a templated OpenAPI 3.1 document with mandatory top-level fields (openapi, info, servers, paths, components) and a documented style for naming paths, parameters, schemas, and responses.
3. Apply security requirements (securitySchemes and global security) consistently; for OAuth 2.0 use RFC 6749 flows and for OpenID Connect use the relevant discovery mechanism.
5. Version each specification using semantic versioning; produce a CHANGELOG entry for every breaking change.
7. Generate clients, server stubs, and documentation from the specification rather than from hand-written code; treat the specification as the source of truth.
9. Validate every specification against the OpenAPI 3.1 JSON Schema prior to publishing; reject specifications that fail validation.

## Controls and evidence
- OpenAPI 3.1 specification repository with version, owner, change log, and last review date.
- Style guide document describing naming conventions, schema patterns, and security requirement patterns.
- Validation pipeline records showing specification identifier, validator version, and validation result.
- Client/server generation log with target language, generated artefact version, and source specification version.

## Validation
- Re-validate all specifications against the OpenAPI 3.1 JSON Schema and confirm zero errors.
- Verify each specification's security requirements align with the studio's authentication and authorization baseline.
- Confirm that generated clients and server stubs match the latest specification version.

## Failure correction
- **Specification fails validation** → block the publishing pipeline, fix the specification, and re-validate.
- **Inconsistency between specification and generated artefact** → regenerate the artefact and reconcile; document the divergence if regeneration is delayed.
- **Security requirement drift** → update the specification, regenerate the artefact, and notify downstream consumers.

## Limitations
- OpenAPI 3.1 is the first release aligned with JSON Schema 2020-12; some tooling may not yet support all features.
- OpenAPI describes HTTP APIs; it does not cover asynchronous or event-driven APIs (use AsyncAPI or equivalent).
- Generating code from a specification does not guarantee that the implementation matches the specification; runtime conformance testing is still required.

## Scope note
This article is part of the templates leaf. Cross-reference: IETF_RFC_8259_JSON_INTERCHANGE_TEMPLATE_GOVERNANCE.md, ASYNCAPI_3_0_SPECIFICATION_TEMPLATE_GOVERNANCE.md, IETF_RFC_7807_PROBLEM_DETAILS_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- OpenAPI Initiative — OpenAPI Specification v3.1.0: https://spec.openapis.org/oas/v3.1.0
- OpenAPI Initiative — OpenAPI Specification v3.0.3: https://spec.openapis.org/oas/v3.0.3
- JSON Schema 2020-12: https://json-schema.org/draft/2020-12/schema
- OpenAPI Style Guide (Microsoft): https://github.com/Azure/azure-api-style-guide
- SmartBear — Spectral OpenAPI linter: https://stoplight.io/open-source/spectral