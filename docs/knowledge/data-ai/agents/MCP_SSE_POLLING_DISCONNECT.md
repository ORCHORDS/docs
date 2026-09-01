# MCP SSE Polling and Disconnect Semantics

## Purpose

MCP Streamable HTTP can use Server-Sent Events (SSE) for responses that may outlive a single HTTP connection. The 2025-11-25 specification explicitly allows a server to close an SSE connection after it has established a resumable event ID, letting the client reconnect rather than forcing the server to hold a long-lived connection open.

## Protocol behavior

When starting an SSE stream, a server should send an event ID early so the client can reconnect with `Last-Event-ID`. After an event ID has been established, the server may close the connection before the final JSON-RPC response is delivered.

If the server intentionally closes before the stream terminates, it should send a standard SSE `retry` field. The client must respect that retry interval before reconnecting.

A disconnect is not a cancellation. Clients that intend to cancel should send the MCP cancellation notification explicitly.

## Resumability pattern

1. Assign stable event IDs to resumable stream events.
2. Persist enough stream state to continue from a reconnecting client's `Last-Event-ID` when resumability is supported.
3. Send an initial event ID before deliberately disconnecting a connection that has not yet delivered the final response.
4. Include an appropriate SSE retry interval when using server-driven polling behavior.
5. Treat network loss and intentional server disconnect the same from the client's reconnect perspective.
6. Terminate the logical SSE stream only after the JSON-RPC response is delivered, the session expires, or another protocol-defined terminal condition occurs.

## Client behavior

Clients should distinguish transport connectivity from request lifecycle. A request remains active across a reconnect unless it is explicitly cancelled or otherwise reaches a terminal state.

Clients should bound retry behavior with application-level timeouts and session expiry handling so a permanently unavailable server cannot create an infinite reconnect loop.

## Message loss

If reliable delivery across disconnects is required, servers should implement resumability and replay from event IDs. Without persisted event state, reconnecting after a disconnect can lose notifications or intermediate messages.

## Failure modes

- Interpreting every disconnect as cancellation can terminate valid long-running requests.
- Reconnecting without `Last-Event-ID` can duplicate or lose events.
- Ignoring the SSE `retry` field can create excessive reconnect traffic.
- Deliberately disconnecting before issuing an event ID prevents reliable polling behavior.
- Keeping every SSE connection open indefinitely can create unnecessary connection pressure when polling semantics would be sufficient.

## Sources

- Model Context Protocol — Transports, revision 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Model Context Protocol — 2025-11-25 changelog: https://modelcontextprotocol.io/specification/2025-11-25/changelog

## Scope note

MCP defines the transport semantics but does not prescribe a specific persistence store, reconnect budget, or infrastructure timeout. Those are deployment responsibilities.