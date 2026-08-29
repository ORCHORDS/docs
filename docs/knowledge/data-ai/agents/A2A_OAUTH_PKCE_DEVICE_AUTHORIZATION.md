# A2A OAuth, PKCE, and Device Authorization

## Purpose

A2A v1.0 modernizes OAuth security declarations. It adds Device Authorization Grant support for constrained clients, adds a `pkce_required` signal for authorization-code flows, and deprecates implicit and resource-owner-password flows.

## Guidance

1. Prefer Authorization Code with PKCE for interactive public clients.
2. Use Device Authorization Grant where the client cannot safely host a normal browser redirect flow.
3. Do not introduce new dependencies on deprecated implicit or password flows.
4. Acquire credentials out of band using the security schemes advertised in the Agent Card.
5. Send credentials through the appropriate HTTP authentication mechanism, not inside A2A message payloads.
6. Scope tokens to the required agent/skills and apply least privilege.
7. Validate redirect URIs, issuer/audience expectations, expiration, and token handling according to the chosen OAuth deployment.

## Sources

- A2A Protocol — What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/
- A2A Protocol — protocol definitions: https://a2a-protocol.org/latest/definitions/
- A2A Protocol — Enterprise Features: https://a2a-protocol.org/latest/topics/enterprise-ready/

## Scope note

A2A advertises supported security schemes. Identity-provider configuration, token policy, and end-user authorization remain deployment-specific responsibilities.
