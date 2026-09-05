# A2A gRPC Protocol Binding Governance

## Purpose

The Agent2Agent (A2A) Protocol v1.0 defines three officially supported
transport bindings: JSON-RPC 2.0, gRPC, and HTTP+JSON/REST. This article
governs the **gRPC protocol binding** described in Chapter 10 of the A2A
specification so that teams adopting A2A over gRPC can anchor their
implementation, interop testing, and operational expectations to the
normative proto definitions rather than inferred behavior.

The article sits beside
[A2A TCK Conformance Governance](A2A_TCK_CONFORMANCE_GOVERNANCE.md) and
covers the wire-format and service-surface concerns; it does not restate
the cross-binding semantic rules that already appear under
`docs/knowledge/data-ai/agents/A2A_*.md`.

## Current status and standard status

- **Protocol release.** A2A v1.0.0 was released on **2026-03-12** and
  A2A v1.0.1 was released on **2026-05-26**. The v1.0.1 release
  contains three spec fixes and is not described as a breaking change.
  Always pin a specific version when making normative claims.
- **Governance.** The A2A project joined the Agentic AI Foundation, a
  Linux Foundation initiative, during 2025–2026.
- **Normative source.** The single authoritative normative definition
  of A2A data objects and request/response messages is
  `specification/a2a.proto` in the A2A repository. Generated artifacts
  such as `a2a.json` and the language SDK stubs are non-normative build
  outputs.
- **gRPC support in the TCK.** The A2A Technology Compatibility Kit
  exercises gRPC, JSON-RPC, and HTTP+JSON transports. Implementations
  that advertise a gRPC interface in the Agent Card should treat TCK
  coverage of that binding as a compatibility baseline, not as a
  certification.

## Normative proto surface

The binding is anchored by one service definition in package
`lf.a2a.v1`. The service exposes eleven RPC methods. The table below
records the exact signatures as published in `specification/a2a.proto`
on `main`; do not paraphrase them when configuring stub generation,
service reflection, or CI fixtures.

| # | RPC | Request | Response |
| --- | --- | --- | --- |
| 1 | `SendMessage` | `SendMessageRequest` | `SendMessageResponse` |
| 2 | `SendStreamingMessage` | `SendMessageRequest` | `stream StreamResponse` |
| 3 | `GetTask` | `GetTaskRequest` | `Task` |
| 4 | `ListTasks` | `ListTasksRequest` | `ListTasksResponse` |
| 5 | `CancelTask` | `CancelTaskRequest` | `Task` |
| 6 | `SubscribeToTask` | `SubscribeToTaskRequest` | `stream StreamResponse` |
| 7 | `CreateTaskPushNotificationConfig` | `TaskPushNotificationConfig` | `TaskPushNotificationConfig` |
| 8 | `GetTaskPushNotificationConfig` | `GetTaskPushNotificationConfigRequest` | `TaskPushNotificationConfig` |
| 9 | `ListTaskPushNotificationConfigs` | `ListTaskPushNotificationConfigsRequest` | `ListTaskPushNotificationConfigsResponse` |
| 10 | `DeleteTaskPushNotificationConfig` | `DeleteTaskPushNotificationConfigRequest` | `google.protobuf.Empty` |
| 11 | `GetExtendedAgentCard` | `GetExtendedAgentCardRequest` | `AgentCard` |

Notes derived from the same proto file:

- Two RPCs are server-streaming (`SendStreamingMessage` and
  `SubscribeToTask`) and share a single streamed message type
  (`StreamResponse`). All other RPCs are unary.
- `CreateTaskPushNotificationConfig` reuses the
  `TaskPushNotificationConfig` message as its request body; this is the
  expected pattern for create-style RPCs over gRPC.
- `DeleteTaskPushNotificationConfig` returns the standard
  `google.protobuf.Empty`, signaling that callers must not rely on a
  payload to distinguish "deleted" from "did not exist". Build delete
  semantics around idempotency instead.

## Chapter 10 sections the binding is structured around

The published A2A v1.0 specification organizes Chapter 10 into the
following sub-areas. When extending tooling, documentation, or
validators, align them to these named sections so cross-binding
consumers can navigate:

- **10.1 Protocol Requirements** — normative requirements for an
  implementation claiming gRPC support.
- **10.2 Service Parameter Transmission** — how A2A-defined service
  parameters such as `A2A-Version` and `A2A-Extensions` travel over the
  binding.
- **10.3 Service Definition** — the gRPC service declaration, including
  the package and the eleven RPCs.
- **10.4 Core Methods** — per-RPC normative behavior for the eleven
  methods listed above (10.4.1 through 10.4.11).
- **10.5 gRPC-Specific Data Types** — payload types whose meaning is
  specific to the gRPC binding, beginning with
  `TaskPushNotificationConfig` (10.5.1).
- **10.6 Error Handling** — the mapping from JSON-RPC error codes to
  gRPC status codes; this is what callers actually observe as a
  non-OK `status.Status`.
- **10.7 Streaming** — server-streaming behavior, including the
  conditions under which `SendStreamingMessage` and `SubscribeToTask`
  close their streams.

Cross-binding rules live elsewhere in the specification:

- The Agent Card field that selects a binding (Section 4.4.6,
  `AgentInterface.protocolBinding`) is an open-form string. The three
  values the A2A project officially supports are `JSONRPC`, `GRPC`, and
  `HTTP+JSON`.
- Version negotiation is governed by the `A2A-Version` service
  parameter and the `VersionNotSupportedError` outcome. Unsupported
  major/minor versions produce this error regardless of binding.
- Authentication and authorization are defined in Chapter 7
  cross-cutting, not Chapter 10. The gRPC binding carries those
  credentials as gRPC metadata.

## Governance pattern

1. Pin `specification/a2a.proto` to a specific A2A release tag
   (for example, the `v1.0.1` tag) and regenerate language stubs from
   that revision. Do not let stub generation track moving `main`.
2. Generate stubs with `buf` against the repository's `buf.yaml`, which
   uses lint category `STANDARD` with `COMMENTS` enabled and a `FILE`
   breaking-change configuration; deviations from this lint posture
   should be deliberate and recorded.
3. Advertise gRPC only when the implementation has been validated
   against the gRPC tests in the A2A TCK. Treat the absence of a TCK
   run as evidence the binding claim is unverified, not as evidence of
   compliance.
4. Map every JSON-RPC error code produced by the implementation to a
   gRPC status per Section 10.6, including the protocol-level codes for
   parse error, invalid request, method not found, invalid params, and
   internal error. Do not collapse distinct A2A errors into a generic
   `UNKNOWN`.
5. For streaming RPCs (`SendStreamingMessage`, `SubscribeToTask`),
   terminate the stream in the conditions Section 10.7 defines, and
   never rely on a single message shape to convey both terminal and
   non-terminal events.
6. Transmit A2A service parameters (`A2A-Version`, `A2A-Extensions`,
   and any future `a2a-`-prefixed parameters) over gRPC metadata, not
   inside message bodies. Apply gRPC metadata normalization to the
   parameter names so they coexist with infrastructure-specific
   metadata.
7. Treat `GetExtendedAgentCard` and the regular `Agent Card` retrieval
   paths as distinct operations: an extended card can reveal
   additional capabilities and should be gated by the same
   authentication and authorization rules as other authenticated
   endpoints.
8. When `DeleteTaskPushNotificationConfig` returns `Empty`, log and
   audit the call but do not infer that a prior config existed; design
   delete callers to be idempotent.

## Failure modes

- Advertising `GRPC` in the Agent Card without exercising the gRPC
  tests in the A2A TCK, leading to interop surprises that surface only
  in cross-vendor testing.
- Treating `google.protobuf.Empty` from
  `DeleteTaskPushNotificationConfig` as evidence a config was present
  and removed.
- Conflating the eleven RPCs with a smaller JSON-RPC surface; some
  JSON-RPC tools may not expose `GetExtendedAgentCard` or
  `SubscribeToTask` over the HTTP+JSON binding, so consumers that
  select the gRPC binding may need features that have no
  one-to-one JSON-RPC equivalent.
- Letting stub generation drift to `main` after the pinned A2A
  release, which can silently introduce new RPCs, rename messages, or
  shift field tags.
- Mapping every A2A error to gRPC `UNKNOWN`; this destroys
  client-side retry and policy enforcement.
- Implementing `SubscribeToTask` without honoring the stream-closure
  conditions in Section 10.7, which leaks resources and prevents
  graceful client reconnect.

## Sources

- A2A Protocol — latest specification landing page: https://a2a-protocol.org/latest/specification/
- A2A Protocol — v1.0.0 specification: https://a2a-protocol.org/v1.0.0/specification/
- A2A project repository (normative proto and changelog): https://github.com/a2aproject/A2A
- Normative proto file: https://github.com/a2aproject/A2A/blob/main/specification/a2a.proto
- A2A Project — Technology Compatibility Kit: https://github.com/a2aproject/a2a-tck
- A2A TCK — SDK Validation Guide: https://github.com/a2aproject/a2a-tck/blob/main/docs/SDK_VALIDATION_GUIDE.md

## Scope note

This article describes the A2A v1.0 gRPC binding as documented in the
project's published specification and normative proto file. It is a
governance reference for teams adopting the binding; it does not
certify, audit, or otherwise evidence that any specific
implementation conforms to the binding, and it does not assert that
ORCHORDS implements or operates an A2A gRPC endpoint.
