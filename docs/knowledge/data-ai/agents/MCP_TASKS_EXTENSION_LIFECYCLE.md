# MCP Tasks Extension Lifecycle

## Purpose

The 2026-07-28 MCP revision moved long-running work into the official `io.modelcontextprotocol/tasks` extension. Tasks let a server return a task handle for work that will complete later instead of forcing every tool call to finish synchronously.

## Lifecycle

A client opts into task-capable behavior through the Tasks extension. When the request is eligible, the server can return a task result instead of the ordinary tool result. The client then drives the task using the extension lifecycle, including status retrieval, updates, and cancellation where supported.

The modern extension is not wire-compatible with the earlier experimental Tasks API from the 2025-11-25 era.

## Practical controls

1. Require explicit Tasks extension support before returning a task handle.
2. Treat task identifiers as scoped references, not as authorization credentials.
3. Re-check caller authorization when task state or results are retrieved.
4. Define terminal states clearly and make repeated status reads idempotent.
5. Support cancellation only where the underlying work can be safely interrupted or compensated.
6. Keep task results bounded and avoid leaking another user's or tenant's task through predictable identifiers.
7. Record task creation, state transitions, cancellation, and result retrieval without logging sensitive payloads unnecessarily.
8. Do not assume compatibility with the retired experimental Tasks lifecycle.

## Current protocol status

The 2026-07-28 release makes Tasks an official extension and replaces the earlier experimental core design. The C# SDK documentation notes that the modern extension requires protocol version 2026-07-28 or later and has no compatibility bridge to the prior experimental API.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP C# SDK — Tasks: https://csharp.sdk.modelcontextprotocol.io/v2/concepts/tasks/tasks.html

## Scope note

Tasks provide protocol lifecycle semantics. Durable execution, persistence, retries, scheduling, and business-level cancellation policy remain implementation concerns.
