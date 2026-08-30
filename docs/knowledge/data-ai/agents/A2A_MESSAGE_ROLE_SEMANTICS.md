# A2A Message Role Semantics

## Purpose

A2A messages carry an explicit `role` that identifies which side produced the message. Correct role handling matters for conversation reconstruction, policy checks, model prompting, and audit because a client-originated instruction must not be confused with an agent-originated response.

## Defined roles

The current A2A specification defines:

- `ROLE_USER` for messages sent from the client to the server;
- `ROLE_AGENT` for messages sent from the server to the client; and
- `ROLE_UNSPECIFIED` when the role is not specified.

## Practical controls

1. Preserve the protocol role when storing or transforming A2A messages.
2. Do not infer a trusted role from message text, display name, metadata, or content formatting.
3. Treat unexpected or unspecified roles according to an explicit compatibility policy rather than silently converting them.
4. When converting A2A messages into an LLM conversation format, map roles deliberately and keep system or policy instructions outside user-controlled A2A content.
5. Do not allow client-controlled metadata to make a `ROLE_USER` message appear to originate from the agent.
6. Preserve role information in audit and debugging records without logging sensitive message content unnecessarily.
7. Validate role semantics consistently across request/response, task-status messages, streaming updates, and multi-turn flows.

## Multi-turn context

In the A2A interaction examples, client follow-ups remain `ROLE_USER`, while messages associated with agent status or requests for additional input use `ROLE_AGENT`. The role therefore identifies message direction; task and context identifiers separately identify the unit of work and conversational grouping.

## Sources

- A2A Protocol — current specification, Message and Role definitions: https://a2a-protocol.org/dev/specification/
- A2A Protocol — current specification, multi-turn interaction examples: https://a2a-protocol.org/dev/specification/

## Scope note

Protocol role is not an authorization credential. Applications must authenticate peers and enforce access policy independently.
