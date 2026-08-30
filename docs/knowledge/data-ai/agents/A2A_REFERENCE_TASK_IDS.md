# A2A Reference Task IDs for Related Context

## Purpose

A2A messages can use `referenceTaskIds` to identify related tasks that provide additional context without asserting that the message is continuing the lifecycle of each referenced task.

## Distinguish the fields

- `taskId` identifies the specific task being continued or refined.
- `contextId` groups messages and tasks in the same conversational context.
- `referenceTaskIds` points to other tasks that may help the agent understand a follow-up request.

The current specification recommends that clients use `referenceTaskIds` to explicitly identify related tasks and that agents use those referenced tasks to understand context and intent.

## Practical controls

1. Treat referenced task IDs as contextual references, not as authorization credentials.
2. Authorize access to every referenced task before exposing its content to the current operation.
3. Reject or ignore a reference the caller is not entitled to access rather than leaking its existence or history.
4. Avoid automatically merging all referenced task histories into an LLM context without relevance and size controls.
5. Keep `taskId` lifecycle behavior separate from `referenceTaskIds`; a related task is not necessarily the task being modified.
6. Preserve tenant and user boundaries when tasks from multiple contexts are referenced.
7. Apply retention and deletion policy consistently so stale task references cannot resurrect removed data.

## Sources

- A2A Protocol — current specification, Multi-Turn Conversation Patterns: https://a2a-protocol.org/dev/specification/
- A2A Protocol — current specification, Message object and `referenceTaskIds`: https://a2a-protocol.org/dev/specification/

## Scope note

Reference relationships help agents reconstruct intent. They do not grant cross-task data access and should always be filtered through the application's authorization and privacy model.
