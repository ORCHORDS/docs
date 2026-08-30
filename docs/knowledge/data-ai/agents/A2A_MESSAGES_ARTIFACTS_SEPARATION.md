# A2A Messages and Artifacts Separation

## Purpose

A2A v1.0 distinguishes conversational Messages from task-result Artifacts. Keeping those roles separate makes task state, output handling, and recovery more predictable.

## Guidance

1. Use Messages for task initiation, clarification, progress information, requests for additional input, and ongoing interaction.
2. Return durable task outputs through Artifacts associated with the Task rather than treating ordinary Messages as the result container.
3. Do not assume every Message is persisted in task history; transient informational messages may be omitted.
4. Do not use streaming Messages as the sole delivery mechanism for critical information because a disconnected client may miss updates.
5. Persist important information in task state, history, or artifacts according to the application's reliability requirements.
6. Document how clients distinguish informational conversation from result data in each supported modality.

## Source

- A2A Protocol v1.0 specification, Message, Task History, and Artifact guidance: https://a2a-protocol.org/dev/specification/

## Scope note

Applications may layer richer conversational or persistence models on top of A2A, but should preserve the protocol's semantic distinction between interaction and task output.
