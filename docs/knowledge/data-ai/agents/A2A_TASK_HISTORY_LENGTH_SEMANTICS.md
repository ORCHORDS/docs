# A2A Task History Length Semantics

## Purpose

A2A v1.0 uses `historyLength` consistently across task retrieval and related operations to let clients bound how much message history is returned.

## Semantics

1. Treat an omitted history length as no client-imposed limit; the server may still apply its own default.
2. Treat a value of zero as a request to omit task history.
3. For positive values, return no more than the requested number of most recent messages; a server may return fewer.
4. Apply the same interpretation across operations that expose `historyLength` so clients do not need endpoint-specific rules.
5. Do not assume every transient message is persisted in task history.
6. Use bounded history for large or sensitive conversations to reduce payload, retention, and accidental disclosure risk.

## Source

- A2A Protocol v1.0 specification, History Length Semantics: https://a2a-protocol.org/dev/specification/

## Scope note

History limits are response-shaping controls. They do not replace authorization, retention policy, or data-minimization controls.
