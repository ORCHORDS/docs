# W3C WoT Architecture 1.1 Template Governance

## Purpose
Establish the governance pattern for templating Web of Things (WoT) Thing Descriptions and Interaction Affordances per the W3C WoT Architecture 1.1 and WoT Thing Description 1.1 specifications.

## Scope
Applies to every Thing Description (TD), Interaction Affordance, and WoT System produced or consumed by the studio, regardless of the underlying transport protocol or runtime environment.

## Workflow
1. Use a templated Thing Description document with mandatory top-level fields (id, title, securityDefinitions, security, properties, actions, events) per W3C WoT TD 1.1.
3. Apply security definitions consistently: for OAuth 2.0 use RFC 6749 flows, for OpenID Connect use the discovery document, and for API keys use the apiKey security scheme.
5. Version each Thing Description using semantic versioning; produce a CHANGELOG entry for every breaking change to interaction affordances.
7. Validate each Thing Description against the W3C WoT TD JSON Schema prior to publication; reject documents that fail validation.
9. Document cross-protocol binding patterns (e.g., HTTP, MQTT, CoAP) and reference the corresponding W3C WoT Profile specifications.

## Controls and evidence
- Thing Description repository with version, owner, change log, and last-review date.
- Validation pipeline records showing TD identifier, validator version, and validation result.
- Security scheme catalogue with required scopes, audience, and token lifetimes.
- Quarterly review of the binding patterns against the latest W3C WoT Profile recommendations.

## Validation
- Re-validate all Thing Descriptions against the W3C WoT TD JSON Schema and confirm zero errors.
- Verify that each TD's security definitions are consistent with the underlying transport's actual security mechanism.
- Confirm that breaking changes to interaction affordances are accompanied by a major version bump and a CHANGELOG entry.

## Failure correction
- **Thing Description fails validation** → block the publishing pipeline, fix the TD, and re-validate.
- **Security scheme mismatch with transport** → suspend the TD, document the mismatch, and update either the security scheme or the transport configuration.
- **Breaking change without major version bump** → reject the change, document the violation, and require a major version bump.

## Limitations
- W3C WoT TD 1.1 is the most recent stable recommendation; some tooling may still target TD 1.0.
- W3C WoT Profiles (e.g., for HTTP, MQTT, CoAP) are evolving; refer to the latest profile document for the chosen transport.
- Thing Descriptions do not enforce runtime behaviour; runtime conformance testing is required to confirm the Thing Description matches the implementation.

## Scope note
This article is part of the templates leaf. Cross-reference: IETF_RFC_8259_JSON_INTERCHANGE_TEMPLATE_GOVERNANCE.md, OPENAPI_3_1_SPECIFICATION_TEMPLATE_GOVERNANCE.md, ASYNCAPI_3_0_SPECIFICATION_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- W3C Web of Things (WoT) Architecture 1.1: https://www.w3.org/TR/wot-architecture11/
- W3C Web of Things (WoT) Thing Description 1.1: https://www.w3.org/TR/wot-thing-description11/
- W3C WoT Profile specification: https://www.w3.org/TR/wot-profile/
- W3C Web of Things (WoT) Discovery: https://www.w3.org/TR/wot-discovery/
- IETF RFC 7252 — The Constrained Application Protocol (CoAP): https://datatracker.ietf.org/doc/html/rfc7252