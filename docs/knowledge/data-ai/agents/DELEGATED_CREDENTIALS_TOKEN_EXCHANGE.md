# Delegated Credentials and Token Exchange for Agents

## Purpose

Agents often need to call downstream services on behalf of a user, workload, or another service. Reusing the original bearer token across every downstream hop can broaden access and make audience boundaries unclear. A safer pattern is to obtain a token specifically intended for the next resource and scope it to the delegated operation.

## Delegation versus impersonation

OAuth 2.0 Token Exchange distinguishes delegation from impersonation. In delegation, an actor operates on behalf of a subject and the resulting security context can preserve both identities. In impersonation, the issued token represents the subject without preserving a separate acting identity in the same way.

Agent systems should choose deliberately between these models. If auditability requires knowing both who authorized an action and which agent or service performed it, preserve actor information rather than collapsing everything into one identity.

## Resource-specific credentials

When an agent calls a downstream resource:

- request credentials for the intended resource or audience;
- request only the scopes needed for that operation;
- avoid forwarding a token minted for another service;
- keep credential lifetime no longer than the delegated work requires;
- preserve subject and actor context where the authorization system supports it;
- re-authorize when the resource, tenant, identity, or action changes; and
- do not place reusable credentials in prompts, memory, traces, or model-visible logs.

RFC 8707 defines the OAuth `resource` parameter so clients can identify the protected resource for which access is requested. RFC 8693 defines OAuth token exchange, including delegation and impersonation semantics, and allows a service to exchange an incoming token for another token appropriate to a downstream service.

## Practical flow

A delegated agent call can follow this sequence:

1. authenticate the user or calling workload;
2. authorize the requested high-level action;
3. determine the exact downstream resource and required scope;
4. exchange or mint a resource-specific credential;
5. call the downstream resource with that credential;
6. discard or expire the delegated credential when the work is complete; and
7. retain an audit record linking subject, actor, resource, decision, and outcome without recording the secret token itself.

## Failure handling

If token exchange or delegated authorization fails, do not silently fall back to a broader credential. Return the authorization failure or request a new approval path. A missing narrow credential is not justification for escalating privilege automatically.

## References

- IETF RFC 8693 — OAuth 2.0 Token Exchange: https://www.rfc-editor.org/rfc/rfc8693
- IETF RFC 8707 — Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707
- IETF RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700

## Scope note

Token exchange is one standards-based mechanism for delegation, not a universal requirement. The correct credential model depends on the identity provider, downstream service, protocol, and trust boundary.
