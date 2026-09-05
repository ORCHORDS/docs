---
title: gRPC Version Governance (Core, Connect, .NET, Java, Go)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: gRPC core documentation (https://grpc.io/docs/); gRPC protocol guide (https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md, https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-H3.md); HTTP/2 RFC 9113; HTTP/3 RFC 9114
---

# gRPC Version Governance (Core, Connect, .NET, Java, Go)

## Scope

This card governs how `orchords-docs` selects, deploys, and operates gRPC services. It is the reference input for any service mesh configuration, observability stack, or load balancer that fronts a gRPC workload.

## Why this card exists

gRPC is a versioning-heavy stack: wire protocol over HTTP/2 (or HTTP/3), with multiple language implementations that ship at independent cadence. Service definitions (`.proto`) have their own `syntax = "proto3"` version and a separate "edition" namespace (`edition = "2023"`, `edition = "2024"`). A KB card that recommends "use gRPC" without binding to a wire version and a proto edition produces a service that drifts on first dependency update.

## Wire-protocol support matrix

| Transport | Status | Reference | Use case |
|---|---|---|---|
| gRPC over HTTP/2 | required baseline | RFC 9113 (HTTP/2) | all production gRPC today |
| gRPC over HTTP/3 | supported | RFC 9114 (HTTP/3), RFC 9220 (WebSocket bootstrap) | optional, mobile or lossy networks |
| gRPC-Web | required for browser | gRPC-Web spec (1.0.0) | browser-to-backend |
| gRPC Connect | optional RPC variant | connectrpc.com | HTTP/1.1, HTTP/2, HTTP/3; per-request JSON or binary |
| Connect Streaming | optional | connectrpc.com | streaming + per-call deadline |
| gRPC-Health | required for service-mesh probes | gRPC health protocol guide (1.0.0) | every gRPC service |

References: `https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md`, `https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-H3.md`, `https://grpc.io/docs/guides/connectivity-semantics-and-api/`.

## Service-definition version support

| Definition family | Status | Notes |
|---|---|---|
| `proto2` | deprecated in production | use only for legacy service surfaces |
| `proto3` (stable) | required baseline | every new file uses `syntax = "proto3"` |
| `edition = "2023"` | supported | protobuf-compiler ≥ 25.x |
| `edition = "2024"` | supported | protobuf-compiler ≥ 28.x |

References: `https://protobuf.dev/editions/`, `https://protobuf.dev/editions/features/`.

## Major implementation matrix

| Implementation | Language | Current version (2026-09-05) | Edition support |
|---|---|---|---|
| `grpc-go` | Go | v1.65+ | 2023, 2024 |
| `grpc-java` | Java | 1.62+ | 2023, 2024 |
| `grpc-dotnet` (Grpc.Net.Client, Grpc.AspNetCore.Server) | .NET | 2.62+ | 2023, 2024 |
| `grpc-cpp` | C++ | 1.62+ | 2023 (2024 pending) |
| `grpc-python` | Python | 1.62+ | 2023, 2024 |
| `grpc-node` (@grpc/grpc-js) | Node.js | 1.10+ | 2023 |
| `grpc-ruby` | Ruby | 1.62+ | 2023 (2024 pending) |
| `connect-go` | Go | 1.16+ | 2023, 2024 |
| `connectrpc.com/connect-kotlin` | Kotlin | 0.6+ | 2023 |
| `connectrpc.com/connect-swift` | Swift | 0.6+ | 2023 |

References: `https://github.com/grpc/grpc/releases`, `https://github.com/connectrpc/connect-go/releases`.

## HTTP/2 semantics governance

gRPC over HTTP/2 requires the following settings:

- **Content-Type**: `application/grpc`, `application/grpc+proto`, `application/grpc-web`, `application/grpc-web+proto`, or `application/connect+proto`, `application/connect+json`.
- **Path**: `/<package>.<Service>/<Method>`.
- **HTTP/2 settings**: initial window size 1 MiB, max frame size 16 384, max concurrent streams ≥ 100.
- **Trailers-only failure**: gRPC uses HTTP/2 trailers for status code and message; never rely on the HTTP/2 status line alone.
- **TE**: client must advertise `trailers`.

References: `https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md`.

## HTTP/3 semantics governance

gRPC over HTTP/3 follows RFC 9220 § 4 (WebSocket-style bootstrap over HTTP/3 extended CONNECT). Policy:

- Use HTTP/3 only when both ends are under controlled network conditions.
- 0-RTT applies to idempotent unary calls only.
- Trailers semantics are preserved (status code + message in HTTP/3 trailer frame).

References: `https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-H3.md`.

## Service-mesh and proxy compatibility

| Mesh / proxy | gRPC support | Required configuration |
|---|---|---|
| Envoy (1.30+) | full HTTP/2, HTTP/3, gRPC, gRPC-Web, Connect | HTTP/2 codec with `allow_connect=true`, `http2_protocol_options.max_concurrent_streams=100` |
| Istio (1.22+) | full | `meshConfig.defaultConfig.protocolDetectionTimeout=5s` |
| Linkerd (2.15+) | full | `proxy.protocolDetectionTimeout=5s` |
| NGINX (1.25+) | HTTP/2 gRPC, partial HTTP/3 | `grpc_pass` directive, HTTP/2 must be the upstreams protocol |
| HAProxy (2.8+) | HTTP/2 gRPC, partial HTTP/3 | `option http-use-htx`, `option h2-zero-copy` |

## Health and observability

- Every gRPC service **must** implement `grpc.health.v1.Health` and report `SERVING` only after its dependencies are healthy.
- Service-mesh probes call `Health.Check` with a 5-second timeout.
- Standard OpenTelemetry semantic conventions apply (`rpc.system = "grpc"`, `rpc.service`, `rpc.method`, `rpc.grpc.status_code`).
- Status codes: `OK (0)`, `CANCELLED (1)`, `UNKNOWN (2)`, `INVALID_ARGUMENT (3)`, `DEADLINE_EXCEEDED (4)`, `NOT_FOUND (5)`, `ALREADY_EXISTS (6)`, `PERMISSION_DENIED (7)`, `RESOURCE_EXHAUSTED (8)`, `FAILED_PRECONDITION (9)`, `ABORTED (10)`, `OUT_OF_RANGE (11)`, `UNIMPLEMENTED (12)`, `INTERNAL (13)`, `UNAVAILABLE (14)`, `DATA_LOSS (15)`, `UNAUTHENTICATED (16)`.

## Mandatory pre-flight (before deploying a new gRPC service)

1. Confirm the proto package version is `proto3` or `edition = "2023"`/`"2024"`.
2. Confirm the language SDK version is within the matrix above.
3. Confirm the service mesh / proxy version supports gRPC over the chosen transport (HTTP/2 or HTTP/3).
4. Confirm `Health.Check` returns `SERVING` after dependency health-check passes.
5. Confirm trailer-only failure is exercised in the integration test suite.
6. Confirm OpenTelemetry semantic conventions are exported (status_code, latency, bytes).

## Sources

- gRPC core documentation: `https://grpc.io/docs/`
- gRPC protocol HTTP/2: `https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md`
- gRPC protocol HTTP/3: `https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-H3.md`
- Protobuf editions: `https://protobuf.dev/editions/`
- Connect-RPC documentation: `https://connectrpc.com/docs/`
- gRPC health protocol: `https://github.com/grpc/grpc/blob/master/doc/health-checking.md`
