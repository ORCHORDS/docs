# A2A Skill Security Requirements

## Purpose

A2A Agent Cards can describe authentication requirements at both the agent level and the individual skill level. Skill-specific `securityRequirements` allow an agent to expose different capabilities under different authentication or authorization expectations without pretending every skill has the same access boundary.

## Security model

The Agent Card declares named `securitySchemes` and corresponding `securityRequirements`. An individual skill can also declare its own `securityRequirements`, overriding or refining the security needed to invoke that capability.

A2A 1.0 security schemes follow the OpenAPI security model and can describe API keys, HTTP authentication, OAuth 2.0, OpenID Connect, and mutual TLS.

## Practical controls

1. Define security schemes once with stable, unambiguous names in the Agent Card.
2. Attach stricter skill-level requirements to capabilities that expose sensitive data or privileged actions.
3. Do not assume successful authentication for one skill authorizes access to every other skill.
4. Validate the chosen credential against the security requirement for the actual requested operation.
5. Keep OAuth scopes or equivalent permission lists narrow enough to represent the skill's intended privilege.
6. Reject ambiguous or unsupported security combinations rather than silently falling back to weaker authentication.
7. Keep public Agent Cards free of credentials, secrets, or internal security material.
8. Re-evaluate cached authorization decisions when Agent Card security requirements change.

## Sources

- A2A Protocol — current specification, AgentSkill and security requirement fields: https://a2a-protocol.org/dev/specification/
- A2A Protocol — current specification, Security Objects and authentication responsibilities: https://a2a-protocol.org/dev/specification/

## Scope note

Agent Card metadata describes protocol requirements. Actual authorization remains the responsibility of the server and its identity and policy systems.
