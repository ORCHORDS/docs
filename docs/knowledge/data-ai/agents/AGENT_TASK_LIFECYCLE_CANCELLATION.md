# Agent Task Lifecycle and Cancellation

## Purpose

Long-running agent work should have an explicit lifecycle. A caller needs to know whether work is pending, running, completed, failed, or cancelled, and should be able to stop work that is no longer wanted or safe to continue.

## Task boundaries

Treat a long-running operation as a task when it cannot reliably complete within one request or when the caller needs progress, cancellation, or later retrieval of the result. Keep the task identifier opaque and scope access to the caller or security context that created or received it.

## Lifecycle design

A practical lifecycle usually includes:

- creation or acceptance;
- pending or queued state;
- active execution;
- terminal success;
- terminal failure; and
- cancellation.

State transitions should be explicit and monotonic where practical. A completed task should not silently become running again, and cancellation should not be reported as successful until the implementation has actually stopped or reached a defined non-cancellable boundary.

## Cancellation

Cancellation should be idempotent from the caller's perspective. Repeating a cancellation request should not create additional work or duplicate side effects.

When cancellation arrives:

1. authenticate and authorize the caller for the task;
2. mark cancellation intent durably if the system is distributed;
3. stop scheduling new sub-operations;
4. interrupt cancellable work;
5. compensate or reconcile partial side effects when required;
6. release temporary resources and credentials; and
7. return a terminal or clearly transitional state.

Some operations cannot be safely interrupted once committed. In those cases, distinguish "cancellation requested" from "cancelled" and document the point of no return.

## Deadlines and budgets

Every task should have bounded execution. Useful controls include:

- wall-clock deadline;
- maximum retry count;
- maximum tool-call count;
- model or compute budget;
- maximum delegated-task depth; and
- maximum inactivity period.

When a budget is exhausted, fail or pause predictably rather than continuing indefinitely.

## Protocol example

The Model Context Protocol 2026-07-28 release moves long-running Tasks into the `io.modelcontextprotocol/tasks` extension. The task lifecycle uses polling through `tasks/get`, supports `tasks/update`, and the release-candidate description documents `tasks/cancel` for cancellation. This is one protocol-specific example of making asynchronous agent work explicit rather than hiding it behind a permanently open request.

## References

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Model Context Protocol — 2026-07-28 release candidate and Tasks lifecycle: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

## Scope note

This article describes reusable lifecycle patterns. Exact task states, cancellation guarantees, compensation rules, and deadlines depend on the protocol and the side effects performed by the workload.
