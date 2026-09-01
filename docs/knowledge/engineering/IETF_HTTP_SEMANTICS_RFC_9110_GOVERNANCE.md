# IETF HTTP Semantics RFC 9110 Engineering Governance

## Purpose

IETF RFC 9110, "HTTP Semantics," is the authoritative specification for the meaning of HTTP methods, status codes, header fields, content negotiation, authentication, and request/response semantics, independent of any specific HTTP version's wire format. Together with RFC 9111 (caching) and RFC 9112 (HTTP/1.1 messaging), it replaces and obsoletes the earlier RFC 7231, 7232, 7234, 7235, and portions of RFC 7230. For engineering teams building or consuming HTTP APIs, RFC 9110 is the primary authority on what a method promises, what a status code asserts, and what a header field means, and it is the document against which API design decisions should be justified. This article summarizes project-neutral engineering use; it does not claim conformance or interoperability certification for any implementation.

## Scope

RFC 9110 governs HTTP semantics as they apply to resources, methods, status codes, representation metadata, content negotiation, authentication, and request context. It is version-neutral: the semantics defined there apply to HTTP/1.1, HTTP/2, and HTTP/3 equally, with each version's mapping document defining how the semantics are carried. It does not define transport security (that is TLS, RFC 8446), nor does it define API design methodology, resource modeling, or versioning strategy; those are engineering decisions built on top of the standard.

Within the engineering knowledge base, this article covers:

- method semantics and safety/idempotency properties;
- status code classes and their conformance meaning;
- header field registration and the requirements for defining new fields;
- content negotiation and representation selection;
- authentication scheme registration;
- validation of correct HTTP usage in APIs; and
- limitations: a semantics standard, not an API design guide or a security architecture.

## Workflow

A team governing HTTP API design against RFC 9110 should treat the specification as the decision authority. The generic workflow is:

1. For each API operation, select the method whose semantics match the operation's effect:
   - GET and HEAD are safe: they must not cause state change beyond incidental logging or accounting;
   - OPTIONS and TRACE are safe by definition;
   - PUT and DELETE are idempotent: repeating the request must have the same effect as a single occurrence;
   - POST is neither safe nor idempotent and is used for processing per the target resource's semantics;
   - CONNECT establishes a tunnel;
   - PATCH applies partial modifications and is defined with its own semantics in RFC 5789.
2. Select status codes from the correct class, using RFC 9110's registered definitions rather than inventing local meanings:
   - 1xx informational, 2xx success, 3xx redirection, 4xx client error, 5xx server error;
   - distinguish 401 (authentication required, or failed) from 403 (authenticated but not authorized);
   - distinguish 404 (no such resource) from 405 (method not supported for that resource) and 410 (gone);
   - distinguish 422 or 400 for validation failures consistently across an API.
3. Use registered header fields per their definition, and follow the registration process in RFC 9110 (and the permanent message header field name registry) before introducing new fields.
4. Apply content negotiation per the standard: Accept, Accept-Encoding, Accept-Language, and the Vary response field, so caches and intermediaries can correctly discriminate representations.
5. Apply authentication via registered schemes (Basic, Bearer, Digest, Negotiate, or others registered in the IANA HTTP authentication scheme registry), following each scheme's requirements rather than ad hoc token handling.
6. Review all API changes for HTTP conformance before release, confirming method, status, and field choices against the specification text.

## Controls and evidence

Governed HTTP API design produces evidence linking each design decision to the standard:

- an API design guide that pins the RFC 9110 revision in use and states the method and status code policy derived from it;
- per-endpoint design records noting the method, its safety/idempotency classification, and the status codes returned for each outcome, with justification where a choice is non-obvious;
- conformance test suites that verify idempotency and safety claims: repeating a PUT, DELETE, or GET must not produce cumulative state change;
- negative-path tests confirming the correct 4xx code is returned for each client error class, rather than a generic 400 or 500 for all failures;
- header field inventories that list every field the API sends or accepts, distinguishing registered fields from extension fields and documenting the registration status of the latter;
- a record of intermediaries and caches in the delivery path, since Vary and caching directives must be coordinated with them per RFC 9111;
- authentication scheme documentation stating which registered scheme is used and how credentials are protected in transit.

## Validation

Validation that an API conforms to RFC 9110 should include:

- automated checks that safe methods do not mutate state, verified by issuing repeated GET/HEAD/OPTIONS requests and comparing resource state;
- automated idempotency checks for PUT, DELETE, and safe methods by issuing repeated requests and comparing responses and state;
- status code review against the specification for every documented outcome, flagging nonstandard or invented meanings;
- header field review confirming registered fields are used per definition and that new fields follow the RFC 9110 registration requirements;
- content negotiation tests with varied Accept headers confirming correct representation selection and Vary population;
- authentication tests confirming correct 401 versus 403 behavior and scheme-conformant challenge headers;
- regression checks whenever HTTP version or intermediary configuration changes, since mappings differ between HTTP/1.1, HTTP/2, and HTTP/3.

## Failure correction

Common failure modes the specification exposes, and the corrective actions each imply:

- Using POST for every operation because it is convenient—the corrective action is reclassifying read operations as GET and true idempotent replacements as PUT, so caches and retries behave correctly.
- Returning 200 with an error body—the corrective action is mapping each failure to its correct 4xx or 5xx code so clients and monitoring can react without parsing bodies.
- Conflating 401 and 403—the corrective action is applying 401 for missing or invalid credentials and 403 for insufficient authorization after successful authentication.
- Non-idempotent PUT implementation, where a retried update duplicates a side effect—the corrective action is implementing true idempotent replacement semantics or documenting the operation as POST.
- Introducing new header fields without registration— the corrective action is either using registered fields or following the registration process before deployment.
- Ignoring Vary, causing caches to serve the wrong representation—the corrective action is populating Vary for every request header that affects representation selection.

## Limitations

RFC 9110 defines semantics, not design taste. An API can be fully conformant and still poorly modeled or hard to use. The specification is deliberately silent on resource naming, hypermedia formats, API versioning policy, and error body structure; those require additional design decisions and, where applicable, other standards such as RFC 9457 (Problem Details). Method safety and idempotency are semantic contracts: the standard defines what implementations may assume, but verifying that a server honors them requires testing. The specification does not secure an API by itself; transport security, authorization models, and secrets handling are governed by TLS, OAuth (RFC 6749 and successors), and organizational security standards. HTTP extensions evolve, and local caches or intermediaries may not implement newer semantics.

## Scope note

This article summarizes project-neutral engineering use of IETF RFC 9110 and RFC 9111. It does not claim implementation, conformance, or interoperability outcomes for any specific API, client, server, or organization.

## Canonical sources

- IETF RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
- IETF RFC 9111 — HTTP Caching: https://www.rfc-editor.org/rfc/rfc9111