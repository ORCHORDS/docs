# MCP Completion Argument Autocomplete Governance

## Purpose

This guide defines security and operational controls for implementing argument completion through the Model Context Protocol (MCP).

Completion improves usability by suggesting values for prompt arguments or resource URI-template arguments as a user types. It can also expose sensitive names, identifiers, paths, or resources if implemented without authorization and disclosure controls. Completion must therefore be treated as an authenticated data-retrieval operation, not as harmless user-interface decoration.

MCP completion does not validate tool arguments and must not be used as a substitute for tool input schemas, server-side validation, authorization, or confirmation before consequential actions.

## Current context/status

This guide targets the MCP specification revision dated **2026-07-28**.

A server advertises support through its `completions` capability. A client requests suggestions with `completion/complete`. The request identifies either a prompt by name or a resource by URI template, supplies the partially entered argument, and may provide other resolved argument values through `context.arguments`.

The completion reference can address:

- `ref/prompt`, using a prompt name; or
- `ref/resource`, using a resource URI template.

A successful result contains at most 100 completion values. It may also include `total` and `hasMore`, allowing a server to indicate that additional matches exist without returning them all.

Protocol errors relevant to completion include:

- `-32601` when the method is unsupported; and
- `-32602` when request parameters are invalid.

Under the 2026-07-28 revision, requests include required `_meta` self-description fields. Implementations should use the schema for that revision rather than copying request shapes from older examples.

Capability negotiation remains essential: clients must not assume that every server supports completion, and servers must not accept completion requests unless they implement the advertised behavior.

## Workflow and controls

### 1. Negotiate and bind capabilities

During initialization, record whether the connected server declares the `completions` capability. The client should expose autocomplete only when that capability is present.

Bind each completion request to the negotiated protocol session and revision. Reject unexpected methods or shapes rather than guessing how to interpret them. A server must ensure that its declared capabilities match its actual handlers.

A client receiving `-32601` should disable or gracefully degrade completion for that connection. It should not repeatedly retry an unsupported method.

### 2. Validate the request structure

Before searching for suggestions, validate:

- the JSON-RPC envelope and current-revision `_meta` requirements;
- the supported reference type;
- prompt name or resource URI template;
- argument name;
- partial argument value;
- structure and limits of `context.arguments`;
- string lengths and character constraints; and
- session, tenant, and principal binding.

Reject malformed or semantically invalid input with `-32602`. Apply maximum request sizes and nesting limits before expensive parsing or lookup.

Do not interpolate untrusted values directly into database queries, shell commands, filesystem paths, regular expressions, directory-service filters, or remote URLs. Use parameterized queries, allowlisted lookup strategies, bounded matching, and canonicalization appropriate to the backing system.

### 3. Authorize every request

Completion is an enumeration surface. Possession of a prompt name or resource template does not grant permission to discover its possible values.

For each request, authorize:

1. the authenticated principal;
2. access to the referenced prompt or resource template;
3. access to the specific argument being completed;
4. access to each candidate value; and
5. use of the supplied context to narrow the candidate set.

Filter candidates before ranking and truncation. Do not fetch an unrestricted global list, return the first 100 values, and rely on the client to hide unauthorized entries.

Authorization must be evaluated per request because roles, group membership, resource ownership, and session context can change. Cache entries should be scoped by principal, tenant, authorization state, reference, argument, and relevant context.

### 4. Limit enumeration and information disclosure

The 100-value protocol maximum is an upper bound, not a target. Return fewer values when sufficient and require a meaningful prefix for sensitive or high-cardinality namespaces.

Defenses against enumeration include:

- minimum partial-input lengths;
- normalized pagination or bounded searches;
- per-user, per-session, and per-network rate limits;
- request-cost limits;
- anomaly detection for systematic prefix scanning;
- generic treatment of inaccessible references;
- limits on wildcard-like input; and
- omission or coarsening of `total` and `hasMore` when they would reveal sensitive population size.

Avoid distinguishable timing, errors, or counts that allow a caller to infer whether an unauthorized customer, repository, account, file, project, or secret-related identifier exists.

Completion results should contain only the value needed for selection. Do not attach credentials, private metadata, access tokens, hidden identifiers, or explanatory text that reveals restricted details.

### 5. Handle context safely

`context.arguments` allows suggestions to depend on other prompt or resource arguments. Treat all such values as untrusted and potentially stale.

The server should:

- validate recognized context keys;
- reject or ignore unexpected keys according to a documented policy;
- reauthorize referenced context values;
- avoid forwarding context to unrelated services;
- minimize values included in logs and traces; and
- prevent cross-tenant or cross-session reuse.

A client should cancel or disregard responses generated for an older argument state. Associate each response with the exact reference, partial value, context, and request generation that produced it.

Do not send stale form values to a server merely because a cached completion component still holds them. This can disclose data after the user switches account, tenant, resource, or conversation.

### 6. Protect rendering and selection

Treat returned completion values as untrusted content even when they originate from a trusted server.

Clients should:

- render values as text rather than executable markup;
- prevent script, terminal-control, bidirectional-text, and link-spoofing effects;
- constrain displayed length and layout;
- preserve a clear distinction between typed and suggested content;
- require an explicit user selection; and
- never auto-submit a prompt, open a resource, or invoke a tool merely because one result remains.

Selection of a suggestion populates an argument only. Any later operation must perform its own validation, authorization, and required user confirmation.

### 7. Control request volume

Interactive completion can produce a request for every keystroke. Clients should debounce requests, cancel superseded work, and cache safe results. Servers should enforce concurrency, execution-time, and backend-query limits regardless of client behavior.

Cache conservatively:

- use short lifetimes for dynamic or sensitive data;
- include authorization identity and tenant in the key;
- include relevant `context.arguments`;
- invalidate on permission changes when feasible;
- never share private result sets across users; and
- avoid persisting sensitive suggestions in browser storage or telemetry.

Rate limiting should return a controlled failure without causing the client to submit partial input or substitute an unrelated cached result.

### 8. Separate completion from validation

A suggested value is not proof that the value remains valid, exists, or is authorized when later used. Resources can be deleted, permissions can change, and context can become stale.

Prompt expansion or resource access must revalidate the selected value at execution time. Tool calls must be validated against the tool's input schema and business rules independently. Completion for prompt and resource arguments does not extend to tool-argument validation merely because the user interface presents both as autocomplete fields.

### 9. Monitor without collecting excess data

Record enough information to detect abuse and diagnose failures:

- method and result status;
- authenticated principal or privacy-preserving identifier;
- tenant and server identity;
- reference type and argument name;
- request duration and candidate count;
- rate-limit and authorization decisions; and
- schema or backend failures.

Avoid logging full partial values, complete context, or returned suggestions by default. These may include personal data, source-code paths, customer names, or confidential resource identifiers. Apply retention limits and access controls to completion telemetry.

## Failure modes

Common failures include:

- advertising the capability without implementing `completion/complete`;
- using a request schema from an older protocol revision;
- accepting unknown prompts, templates, or argument names;
- authorizing the prompt but not individual suggestion values;
- exposing restricted identifiers through counts, timing, or `hasMore`;
- returning more than 100 values;
- ranking or truncating before authorization filtering;
- caching results across users or tenants;
- forwarding stale `context.arguments` to an external service;
- logging sensitive partial input and candidate values;
- rendering suggestions as markup;
- automatically submitting a selected or sole suggestion;
- treating autocomplete output as tool-input validation;
- retrying `-32601` indefinitely;
- collapsing `-32602`, authorization denial, timeout, and empty results into the same misleading user state; and
- allowing unbounded prefix scans to overload a directory, database, or third-party API.

When completion is unavailable, clients should preserve manual entry where valid and clearly indicate that suggestions—not the underlying prompt or resource operation—are unavailable.

## Evidence and review

An implementation review should include:

- initialization evidence showing capability negotiation;
- schema-conformance tests for the 2026-07-28 revision;
- tests for required `_meta` request fields;
- valid prompt and resource completion examples;
- `-32601` and `-32602` handling;
- verification of the 100-value maximum;
- authorization tests across users, roles, and tenants;
- tests proving filtering occurs before truncation;
- enumeration and timing-abuse tests;
- cache-isolation and invalidation tests;
- stale-response and cancellation tests;
- rendering tests with hostile Unicode and markup;
- confirmation that selection does not auto-submit;
- load tests for debounce, rate limits, and backend bounds; and
- telemetry review demonstrating sensitive values are minimized.

Repeat the review when adopting a new MCP revision, changing identity boundaries, adding completion-backed data sources, or modifying prompt and resource definitions.

## Sources

- [MCP Specification, revision 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [MCP Completion utility](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/completion)
- [MCP 2026-07-28 TypeScript schema](https://github.com/modelcontextprotocol/specification/blob/main/schema/2026-07-28/schema.ts)

## Scope note

This article addresses governance for MCP prompt and resource argument completion under the 2026-07-28 specification revision. It does not define tool argument validation, replace application authorization, or guarantee compatibility with earlier or later revisions. Implementers should verify behavior against the current normative specification and schema used by both client and server.
