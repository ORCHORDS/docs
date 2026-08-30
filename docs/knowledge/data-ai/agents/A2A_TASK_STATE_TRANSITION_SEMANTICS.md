# A2A Task State Transition Semantics

## Purpose

A2A tasks move through explicit states that describe whether work is queued, in progress, waiting for more input or authorization, or finished. Clients should respond to the declared task state rather than infer lifecycle status from message text or artifact presence.

## State classes

The current specification includes in-progress states such as `TASK_STATE_SUBMITTED` and `TASK_STATE_WORKING`, interrupted states including `TASK_STATE_INPUT_REQUIRED` and `TASK_STATE_AUTH_REQUIRED`, and terminal states including `TASK_STATE_COMPLETED`, `TASK_STATE_FAILED`, `TASK_STATE_CANCELED`, and `TASK_STATE_REJECTED`.

## Practical controls

1. Store task state separately from free-form status messages.
2. Treat terminal states as final for the task unless the protocol explicitly defines another operation that creates new work.
3. When `TASK_STATE_INPUT_REQUIRED` is returned, continue with the same task/context identifiers instead of silently creating unrelated work.
4. When `TASK_STATE_AUTH_REQUIRED` is returned, complete the required authorization flow before retrying privileged work.
5. Do not treat artifact presence as proof that the task completed successfully; inspect the declared state.
6. Make repeated polling and streamed state processing idempotent.
7. Reject invalid state values rather than inventing local aliases that create cross-implementation ambiguity.
8. Preserve state transitions in audit data where lifecycle evidence matters.

## Return behavior

For blocking message execution, A2A waits until the task reaches a terminal or interrupted state before returning. With non-blocking execution, the caller can receive an in-progress task and is responsible for retrieving later updates through polling, streaming, or push notifications.

## Sources

- A2A Protocol — current specification, task execution and return behavior: https://a2a-protocol.org/dev/specification/
- A2A Protocol — current specification, task-state validation and multi-turn interaction examples: https://a2a-protocol.org/dev/specification/

## Scope note

Protocol states do not define application-level retry policy, business compensation, persistence guarantees, or user-facing workflow terminology.
