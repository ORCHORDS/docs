# MCP Multi Round-Trip Requests

## Purpose

MCP 2026-07-28 replaces in-flight server-to-client JSON-RPC requests with Multi Round-Trip Requests (MRTR). This lets a stateless server ask for elicitation, sampling, or roots information without holding a bidirectional transport open.

## Flow

When more client input is needed, a server returns an `input_required` result containing the required requests and opaque request state. The client obtains the requested input and retries the original operation with `inputResponses` and the unchanged request state.

## Implementation guidance

1. Treat `requestState` as opaque and round-trip it exactly.
2. Bound the number of interactive rounds so malformed or adversarial flows cannot loop indefinitely.
3. Re-run authorization and validation on each retried request rather than assuming an earlier round grants continuing authority.
4. Preserve correlation identifiers across rounds for observability while using fresh request identifiers where the SDK/spec requires them.
5. Do not expose hidden server state in request-state values unless it is intentionally protected and safe for the client to carry.
6. Make cancellation and timeout budgets apply to the overall interaction, not independently to every round.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP TypeScript SDK — supporting protocol revision 2026-07-28: https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28

## Scope note

MRTR is protocol machinery for interactive request/response workflows. Product UX, consent policy, and application-specific authorization remain separate concerns.
