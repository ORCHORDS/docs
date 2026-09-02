# IETF RFC 9290 Problem Reports for HTTP APIs Template Governance

## Purpose
Establish the governance pattern for templating HTTP problem report responses per IETF RFC 9290 (Problem Details for HTTP APIs) and related RFC 7807 legacy guidance, including problem type identifiers and extension members.

## Scope
Applies to every HTTP API produced by the studio that returns error responses, regardless of whether the API is public or internal.

## Workflow
1. Use a templated problem details document with mandatory fields (type, title, status, detail, instance) per RFC 9290; the type field should be a URI that, when dereferenced, yields human-readable documentation for the problem type.
3. Define a controlled vocabulary of problem type URIs in the studio's API catalogue, with stable identifiers, owner, and documentation.
5. Use the instance field to provide a URI reference identifying the specific occurrence of the problem (e.g., a request ID URI); do not include sensitive data in the instance URI.
7. Use extension members for problem-specific details (e.g., errors array with per-field validation failures); document each extension in the API contract.
9. For backward compatibility, accept RFC 7807 problem details documents but emit RFC 9290 documents for new errors.

## Controls and evidence
- Problem type catalogue with URI, title, status code, description, and documentation link.
- API contract entry for each endpoint specifying the problem types it may emit.
- Extension member catalogue with field name, type, semantics, and stability classification.
- Quarterly review of the problem type catalogue against the latest API catalogue.

## Validation
- Re-validate a sample of 10 problem type documents against the RFC 9290 requirements and confirm zero errors.
- Verify that each problem type URI is dereferenceable and returns human-readable documentation.
- Confirm that extension members are documented in the API contract and that the API consumer can rely on stable field names.

## Failure correction
- **Problem type URI not dereferenceable** → publish the documentation page, document the gap, and notify API consumers.
- **Extension member undocumented** → document the extension in the API contract, version the contract, and notify consumers.
- **Inconsistency between RFC 7807 and RFC 9290 responses** → standardize on RFC 9290 for new errors, document the migration, and accept both during the transition.

## Limitations
- RFC 9290 inherits RFC 7807; legacy clients may still parse RFC 7807 problem details documents, which have the same JSON structure.
- Problem type URIs should be stable; changing a problem type URI is a breaking change for API consumers.
- Problem details documents do not replace server-side logging; continue to record detailed error information in server logs.

## Scope note
This article is part of the templates leaf. Cross-reference: IETF_RFC_8259_JSON_INTERCHANGE_TEMPLATE_GOVERNANCE.md, OPENAPI_3_1_SPECIFICATION_TEMPLATE_GOVERNANCE.md, ASYNCAPI_3_0_SPECIFICATION_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- IETF RFC 9290 — Problem Details for HTTP APIs: https://datatracker.ietf.org/doc/html/rfc9290
- IETF RFC 7807 — Problem Details for HTTP APIs (obsoleted by RFC 9290): https://datatracker.ietf.org/doc/html/rfc7807
- IETF RFC 7231 — Hypertext Transfer Protocol (HTTP/1.1): https://datatracker.ietf.org/doc/html/rfc7231
- IETF RFC 9110 — HTTP Semantics: https://datatracker.ietf.org/doc/html/rfc9110
- OpenAPI Initiative — OpenAPI Specification v3.1.0: https://spec.openapis.org/oas/v3.1.0