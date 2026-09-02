# IETF RFC 8615 Well-Known URI Template Governance

## Purpose
Establish the governance pattern for templating well-known URIs per IETF RFC 8615 (Well-Known Uniform Resource Identifiers (URI)), including registration, discovery, and security considerations.

## Scope
Applies to every well-known URI exposed by the studio for service discovery, configuration, or policy advertisement, regardless of the underlying transport protocol.

## Workflow
1. Use a templated well-known URI registration record with mandatory fields: URI suffix, change controller, specification document, and access policy (public, restricted, or authenticated).
3. For each well-known URI, maintain a specification document describing the resource representation, the access policy, and the stability classification.
5. Version each well-known URI response using media-type versioning or content versioning as specified by the relevant specification; reject clients that consume an unknown version.
7. Document the security considerations of the well-known URI per RFC 8615 §4 and the relevant specification; restrict access as needed.
9. Maintain a registry of well-known URIs deployed by the studio with change controller, specification URL, and last review date.

## Controls and evidence
- Well-known URI registry with URI suffix, change controller, specification URL, and access policy.
- Specification document for each well-known URI describing the response format, version, and security considerations.
- Access control log for restricted well-known URIs showing access pattern and policy enforcement.
- Quarterly review of the well-known URI registry against the latest IANA registrations.

## Validation
- Re-validate a sample of 10 well-known URIs against their specification documents and confirm zero errors.
- Verify each well-known URI's access policy matches the deployed configuration.
- Confirm that restricted well-known URIs return 401/403 when accessed without authentication.

## Failure correction
- **Well-known URI response does not match specification** → suspend the endpoint, document the gap, and remediate before reactivating.
- **Access policy drift** → tighten the access control, document the drift, and audit prior access for impact.
- **Specification document missing or outdated** → refresh the specification, document the staleness window, and notify consumers.

## Limitations
- RFC 8615 defines the well-known URI convention; the resource representation is defined by individual specifications (e.g., RFC 8414 for OAuth authorization server metadata).
- Well-known URIs are intentionally long-lived; changing a well-known URI path is a breaking change for clients.
- Some specifications (e.g., security.txt per RFC 9116) have additional policy requirements that must be observed.

## Scope note
This article is part of the templates leaf. Cross-reference: IETF_RFC_8259_JSON_INTERCHANGE_TEMPLATE_GOVERNANCE.md, OPENAPI_3_1_SPECIFICATION_TEMPLATE_GOVERNANCE.md, IETF_RFC_8141_URN_2024_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- IETF RFC 8615 — Well-Known Uniform Resource Identifiers (URI): https://datatracker.ietf.org/doc/html/rfc8615
- IANA — Well-Known URIs registry: https://www.iana.org/assignments/well-known-uris/well-known-uris.xhtml
- IETF RFC 8414 — OAuth 2.0 Authorization Server Metadata: https://datatracker.ietf.org/doc/html/rfc8414
- IETF RFC 9116 — A File Format to Aid in Security Vulnerability Disclosure: https://datatracker.ietf.org/doc/html/rfc9116
- IETF RFC 7033 — WebFinger: https://datatracker.ietf.org/doc/html/rfc7033