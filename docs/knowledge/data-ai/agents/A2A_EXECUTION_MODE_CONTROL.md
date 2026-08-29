# A2A Execution Mode Control

## Purpose

A2A v1.0 lets a client distinguish between waiting for task completion and returning promptly with a task that can be observed later. This makes latency expectations explicit instead of coupling every agent interaction to one blocking behavior.

## Guidance

1. Use completion-waiting mode only when expected execution time fits the caller's timeout and user experience.
2. Prefer immediate-return task handling for long-running work.
3. When returning a task, persist enough state for later status retrieval without exposing secrets in task identifiers.
4. Make cancellation and authorization decisions valid across the task lifetime.
5. Surface task state clearly instead of treating an accepted task as completed work.
6. Define retry/idempotency behavior so a caller does not accidentally create duplicate long-running tasks.
7. Apply workload limits independently of whether the client waits synchronously.

## Sources

- A2A Protocol — What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/
- A2A Protocol — current specification: https://a2a-protocol.org/dev/specification/

## Scope note

Execution mode controls response timing and task lifecycle behavior. It does not change the permissions required to perform the requested action.
