# MCP Sampling with Tools

## Purpose

Model Context Protocol sampling lets an MCP server ask the client to perform an LLM generation while the client retains control over model access, selection, permissions, and user interaction. The 2025-11-25 MCP specification adds tool use to sampling so servers can implement multi-step agentic loops without receiving the client's model-provider API key.

## Capability negotiation

A client that supports basic sampling declares the `sampling` capability during initialization. Tool-enabled sampling is a separate capability: the client declares `sampling.tools` before a server may send sampling requests that contain tool definitions.

Servers MUST NOT send tool-enabled sampling requests to clients that have not declared support for `sampling.tools`.

## Tool-enabled request flow

A server can include a `tools` array and optional `toolChoice` in `sampling/createMessage`. The client's model may return tool-use requests, the client executes or mediates those tools according to its own policy, and tool results are fed back into the sampling conversation until a final response is produced.

The protocol permits provider-specific implementations underneath this flow, but provider controls such as disabling parallel tool calls are not part of the core MCP specification unless exposed through an extension.

## Message-balance rule

MCP requires every assistant sampling message containing tool-use blocks to be followed by a user message consisting entirely of matching tool-result blocks before other message content continues. Each tool-use identifier must be matched by its corresponding result.

This invariant should be validated before forwarding provider output into another provider or into persisted conversation state.

## Security and user-control pattern

1. Treat tool-enabled sampling as a higher-capability mode than text-only sampling.
2. Preserve the client's policy boundary: the server requests sampling, but the client decides whether and how the model and tools are used.
3. Present sampling requests to the user when human review is part of the client policy.
4. Allow users to inspect or edit prompts where the client supports that interaction model.
5. Apply ordinary tool authorization, least privilege, rate limiting, and data-minimization rules inside the sampling loop.
6. Do not assume a server-requested tool definition is safe merely because it arrived through a valid MCP session.
7. Bound loop depth, execution time, tool count, and token/resource consumption so nested agentic behavior cannot grow without limit.
8. Preserve tool-use/result pairing in logs and traces without exposing secrets or unnecessary tool payloads.

## Context control

The `includeContext` values that automatically include context from this server or all servers are soft-deprecated in the 2025-11-25 specification. Servers should prefer explicit prompts and avoid requesting additional context unless the client has declared the relevant capability and the extra data is actually needed.

## Failure modes

- Sending tool-enabled sampling to a client that did not advertise support is a protocol violation.
- Treating sampling tools as server-owned credentials bypasses the intended client-control boundary.
- Losing tool-use/result pairing can make provider conversations invalid or ambiguous.
- Allowing unrestricted recursive sampling can create cost, latency, and denial-of-service risks.
- Automatically including broad cross-server context can disclose information beyond the task's need.

## Sources

- Model Context Protocol — Sampling, protocol revision 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25/client/sampling
- Model Context Protocol — 2025-11-25 changelog: https://modelcontextprotocol.io/specification/2025-11-25/changelog
- MCP Blog — November 2025 specification release: https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/

## Scope note

MCP standardizes the sampling message flow and capability negotiation. Model-provider safety controls, tool execution sandboxes, pricing, and human-review UX remain client-implementation responsibilities.