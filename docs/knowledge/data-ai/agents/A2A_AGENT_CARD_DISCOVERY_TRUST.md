# A2A Agent Card Discovery and Trust

## Purpose

The Agent2Agent (A2A) Protocol uses an Agent Card as the discovery document that describes an agent's identity, capabilities, skills, supported interfaces, service endpoint, and authentication requirements. A2A v1.0 is the current stable protocol line.

## Discovery model

A client can discover an Agent Card through a well-known URI, a registry or catalog, or direct configuration. For well-known discovery, the protocol defines `/.well-known/agent-card.json` on the agent's origin.

Treat discovery metadata as security-relevant configuration rather than harmless presentation data. A client should validate the origin it intended to contact, use HTTPS, apply normal trust and allow-list policy, and avoid automatically granting privileges merely because an Agent Card advertises a skill.

## Sensitive and extended cards

Public Agent Cards should not contain secrets or unnecessary internal implementation details. When richer metadata is sensitive, A2A supports authenticated extended Agent Cards. Access controls for those documents should be evaluated independently from access to the agent's task interface.

A2A also defines signatures for Agent Cards. When signatures are present, clients should verify them according to their trust policy before using card contents for routing or authorization decisions.

## Practical checklist

1. Discover the card only from an expected origin or trusted registry.
2. Verify HTTPS and any configured certificate or network trust requirements.
3. Parse declared skills, interfaces, and authentication requirements as untrusted input until validated.
4. Do not place static credentials in an Agent Card.
5. Protect authenticated extended cards with explicit authorization.
6. Verify card signatures when the deployment relies on signed metadata.
7. Re-evaluate cached cards when their origin, version, signature, or security requirements change.

## Sources

- A2A Protocol — v1.0 documentation and specification: https://a2a-protocol.org/v1.0.0/
- A2A Protocol — specification repository: https://github.com/a2aproject/A2A/blob/main/docs/specification.md

## Scope note

This article describes protocol-level discovery and trust considerations. It does not prescribe a specific PKI, registry, or organizational trust model.
