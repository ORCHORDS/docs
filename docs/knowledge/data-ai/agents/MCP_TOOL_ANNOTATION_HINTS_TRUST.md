# MCP Tool Annotation Hints and Trust Boundaries

## Purpose

This article defines a project-neutral governance model for tool annotation hints exposed by Model Context Protocol (MCP) servers and consumed by MCP clients. Its objective is to prevent annotation hints from being treated as authorization signals, while preserving their usability value for user interface rendering and confirmation flows.

## Current status

As of the MCP specification revision dated **2026-07-28**, the `Tool` definition includes an optional `annotations` object that conveys descriptive hints. Hints are advisory metadata, not capability declarations, and the protocol states that servers must not use them as a substitute for authorization.

An MCP server may declare any subset of the documented hint fields. Common hint fields include `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`, and similar descriptive properties. The full schema is published with the specification.

Annotations are designed to help clients render better affordances and confirmation prompts. The protocol explicitly cautions clients that hints are untrusted with respect to authorization because the server controls them and they may be inaccurate, incomplete, or adversarial.

Servers do not have to declare annotations. Clients do not have to honor them. Hosts should evaluate the protocol-level tool registration, the negotiated capabilities, and the host’s own authorization layer for actual security decisions.

## Trust boundary

The MCP trust boundary places the host application and the user between the client and the server for consequential decisions. Annotations cross this boundary as descriptive text only.

Practical consequences:

1. Hints are written by the server. The server can claim or omit whatever it chooses.
2. Hints are read by the client to influence UI affordances and default behavior.
3. The user is the final decision authority for consequential operations, regardless of any hint.
4. The host retains responsibility for its own permission model, identity, secrets, audit logging, and policy enforcement.

A client must not implement behavior whose security would be undermined by an honest or dishonest server lying in its own annotations.

## Required client controls

### 1. Treat hints as untrusted metadata

Clients must parse annotation hints as user interface metadata, not as policy. The client should:

- validate annotation shape against the published schema;
- ignore unknown fields rather than guessing their meaning;
- normalize values into internal data structures that cannot be confused with authorization tokens;
- keep annotations visually separated from security-sensitive messaging such as identity, origin, or trust indicators; and
- never use an annotation to grant, expand, or revoke a permission.

The default posture for a missing or unrecognized hint is to behave as if the safest possible default applies. A missing `readOnlyHint` should not be interpreted as permission to mutate state. A missing `destructiveHint` should not be interpreted as permission to perform destructive work without confirmation.

### 2. Fail closed on contradictory or hostile hints

A client must reject or safely normalize annotations that:

- contradict the tool’s input schema;
- contradict the tool’s name, description, or category;
- contain markup, control characters, or homograph text that could mislead the user;
- imply capabilities outside the protocol (for example, claiming to bypass authorization); or
- are structurally invalid under the current MCP schema.

The client should record the rejection, the tool identifier, and the reason in audit logs where it exists. The user should still see the tool’s declared name and description but should not be misled by the rejected hint.

### 3. Keep hints out of the authorization path

Authorization decisions belong to the host, not to annotations. Clients must:

- evaluate their own permission model before invoking a tool;
- require explicit user confirmation for destructive, irreversible, or high-impact operations regardless of `destructiveHint`;
- enforce rate limits and budget controls at the host layer;
- gate tool calls on independent identity, tenancy, and policy checks; and
- record the actual authorization decision in audit logs, not the hint that may have influenced UI.

A client should never collapse "user dismissed the confirmation prompt" into "user consented" or interpret the absence of a confirmation prompt as consent.

### 4. Render hints for UX only

Annotations exist to make user interfaces clearer. Acceptable uses include:

- adjusting confirmation copy ("This action modifies or deletes data");
- deciding whether to show a tool as read-only or mutating in a chooser;
- enabling or disabling default invocation patterns when the user has opted into such behavior;
- surfacing idempotency expectations to the user; and
- grouping tools in listings.

Unacceptable uses include:

- auto-invoking a tool without user action because `readOnlyHint` is true;
- skipping confirmation because `destructiveHint` is false or absent;
- retrying an operation indiscriminately because `idempotentHint` is true;
- treating `openWorldHint` as permission to send data to arbitrary external systems; and
- storing hint text as a security classification label.

### 5. Validate server provenance

The client should record and consider the provenance of the server it is connecting to:

- the server identity and version, where the host tracks it;
- the transport and origin of the connection;
- the trust level the host assigns to that server (for example, first-party, vetted, unverified);
- the negotiation revision; and
- the capabilities actually advertised at initialization.

A hint from an unverified or sandbox server should be rendered with stronger cautions than the same hint from a first-party server that the host has validated.

## Required server controls

### 1. Declare hints honestly and minimally

A server should publish only the annotations it can support with reasonable confidence. Honesty reduces the probability of accidental harm and supports user trust.

Servers should:

- publish `title` only when it is a stable human-readable label;
- set `readOnlyHint` true only when the tool does not modify state;
- set `destructiveHint` true when the tool may delete or replace data, even if it does not always do so;
- set `idempotentHint` true only when repeated calls with identical inputs have no additional effect beyond the first call;
- set `openWorldHint` true when the tool may interact with external systems or unknown inputs beyond the server’s control; and
- omit fields that the server cannot speak to with confidence.

Hints that change unpredictably across calls undermine their usefulness. Servers should treat annotations as part of the tool’s contract.

### 2. Separate hints from behavior

Servers must implement tool behavior independently of the hint metadata they publish. A tool marked `readOnlyHint: true` must not write data; a tool marked `destructiveHint: true` must be capable of performing the destructive operation when authorized; and so on. Clients should be able to rely on the declared hint as a behavioral expectation.

Servers should avoid implementing "advisory" or "best-effort" hint behavior in which the hint is correct most of the time but not always. Hosts cannot enforce probabilistic honesty.

### 3. Do not extend hints into a covert channel

Hints must not be used to:

- smuggle instructions to the client or model that bypass the host’s policy;
- encode data that the server cannot legitimately transmit;
- mark a tool as "safe" in order to suppress normal review; or
- mark a tool as "dangerous" in order to discourage otherwise legitimate use.

Servers whose hints appear designed to manipulate client behavior should be treated as misbehaving and may be disconnected by the host.

## Failure modes

Common failures include:

- treating `readOnlyHint: true` as authorization to call the tool without user consent;
- skipping confirmation prompts when `destructiveHint` is missing;
- retrying a tool freely because `idempotentHint` is true, without verifying identical inputs;
- inferring network reachability or external integration from `openWorldHint`;
- using hint text as a classification label in security tooling;
- storing hints in long-lived caches after the server registration has changed;
- inheriting hints across server versions or after capability renegotiation without revalidation;
- presenting hints as if they were issued by the host rather than the server; and
- logging full hint text together with sensitive identity or payload context.

## Evidence and review

A host’s review of hint handling should include:

- sample tools advertising each hint value;
- sample tools omitting hints;
- tools with contradictory hints;
- tools whose declared hint disagrees with observed behavior in logs;
- prompt-injection attempts embedded in hint text;
- cache-invalidation tests across server restarts and capability renegotiation;
- audit-log reviews confirming hints never appear in authorization decisions; and
- confirmation-prompt enforcement tests for destructive operations.

Repeat the review whenever the MCP revision changes, when a new server class is onboarded, when transport or origin policies change, or when the host’s authorization model changes.

## Sources

- [MCP Specification, revision 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [MCP server tools reference](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [MCP 2026-07-28 TypeScript schema](https://github.com/modelcontextprotocol/specification/blob/main/schema/2026-07-28/schema.ts)

## Scope note

This article is governance guidance for tool annotation hints under the MCP 2026-07-28 specification revision. It does not replace the host application’s authorization model, transport security, or audit obligations. Implementers should verify behavior against the current normative specification and schema in use.
