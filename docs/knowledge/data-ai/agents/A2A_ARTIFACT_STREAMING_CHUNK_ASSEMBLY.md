# A2A Artifact Streaming and Chunk Assembly

## Purpose

A2A v1.0 can stream task artifact updates incrementally. `TaskArtifactUpdateEvent` uses an artifact identifier together with `append` and `lastChunk` semantics so clients can assemble a result without confusing partial output with the completed artifact.

## Controls

1. Correlate updates by task, context, and artifact identifier.
2. When `append` is true, append the update to the previously received artifact with the same identifier rather than replacing it.
3. Treat `lastChunk` as the completion signal for that artifact stream when present.
4. Preserve part order and media-type information while assembling chunks.
5. Reject or quarantine updates that cannot be correlated safely to the expected task and artifact.
6. Do not expose an assembled artifact as complete until the protocol state indicates completion or the application has another explicit completeness rule.
7. Test duplicate, missing, reordered, and interrupted delivery scenarios.

## Source

- A2A Protocol v1.0 specification, TaskArtifactUpdateEvent: https://a2a-protocol.org/dev/specification/

## Scope note

The protocol defines update semantics; storage durability, resumability, integrity hashes, and application-level replay behavior remain implementation concerns.
