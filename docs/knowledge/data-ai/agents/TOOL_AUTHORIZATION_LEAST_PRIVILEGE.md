# Agent Tool Authorization and Least Privilege

## Why it matters

Agentic systems can call tools that read data, modify state, send messages, or invoke external services. Tool access should therefore be treated as an authorization boundary rather than as a prompt-design concern.

## Core principles

- grant an agent only the tools and scopes needed for the current task;
- keep authorization decisions outside model-generated text;
- validate tool arguments before execution;
- separate read-only capabilities from state-changing capabilities;
- require stronger approval for irreversible or high-impact operations;
- bind credentials to the narrowest practical audience and scope;
- avoid passing long-lived secrets through model context;
- re-check authorization when identity, tenant, tool, or requested action changes; and
- record tool calls and authorization outcomes without exposing secrets.

## OAuth and delegated access

Where a tool uses OAuth, the authorization server remains responsible for authenticating the resource owner and issuing scoped access tokens. An agent should not infer or expand scopes on its own. Resource servers should validate tokens for the intended audience and requested operation.

The current Model Context Protocol specification, released 2026-07-28, further hardens authorization. Among its changes, MCP clients validate the authorization-server issuer in authorization responses, and the protocol continues moving toward explicit, resource-scoped authorization rather than reusable bearer credentials crossing service boundaries.

## Execution boundary

A safe tool gateway should perform, in order:

1. identify the caller and relevant tenant or security context;
2. resolve the requested tool to a fixed implementation;
3. validate arguments against the tool schema and business rules;
4. authorize the specific action;
5. obtain or use the minimum required credential;
6. execute the operation;
7. return only the minimum necessary result; and
8. emit an auditable record of the decision and outcome.

Model output can propose an action, but it should not be the final authority for whether that action is permitted.

## Approval boundaries

Human approval is especially useful when an action is costly, destructive, legally significant, privacy-sensitive, externally visible, or difficult to reverse. Approval should cover the concrete action and parameters rather than a vague instruction such as "do whatever is necessary."

## References

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- IETF RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700
- IETF RFC 8707 — Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707
- IETF RFC 6749 — The OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749

## Scope note

This article describes reusable design principles. Exact authorization requirements depend on the protocol, deployment model, service, and applicable security policy.
