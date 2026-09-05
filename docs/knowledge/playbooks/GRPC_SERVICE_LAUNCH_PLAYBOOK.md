# gRPC Service Launch Playbook

## Purpose

Stand up a new gRPC service in the `orchords-docs` reference architecture end-to-end: proto definition, code generation, server bootstrap, observability wiring, and on-call runbook. The playbook avoids the common failure modes of gRPC adoption (incompatible transport versions, missing health check, status-code misuse).

## Audience

Platform engineers, service-mesh operators, on-call SRE.

## Pre-conditions

1. The service definition is `proto3` or `edition = "2023"`/`"2024"`.
2. The language SDK version is within the matrix in `GRPC_VERSION_GOVERNANCE.md`.
3. The transport is HTTP/2 (default) or HTTP/3 with documented network-conditions justification.
4. The service mesh (Envoy, Istio, Linkerd) supports gRPC over the chosen transport.
5. The proto package is registered with the proto registry (Buf Schema Registry or in-tree).

## Procedure

### 1. Proto definition

1. Add the proto file under `proto/<package>/v<n>/<service>.proto`.
2. Pin the package version in the file path (e.g., `orchords/docs/v1/`).
3. Document every field with a comment that includes units and constraints.
4. Run `buf lint`, `buf breaking --against '<previous-git-rev>'`, and `protolock` against the registry.
5. Generate code for every language SDK in the matrix above. Commit generated code to the repo.

### 2. Server bootstrap

1. Implement the service interface with bounded concurrency (interceptors, deadline propagation).
2. Register `grpc.health.v1.Health` and report `SERVING` only after dependencies are healthy.
3. Register `grpc.reflection.v1alpha.Reflection` in non-production environments.
4. Set explicit deadlines on every server-side call into dependencies.
5. Set `max_connection_idle_ms`, `max_concurrent_streams`, and `initial_window_size` to project standards.

### 3. Status codes and trailers

Map every internal error to the gRPC status code in the policy table:

| Internal failure | gRPC status |
|---|---|
| Validation failure | `INVALID_ARGUMENT (3)` |
| Auth failure | `UNAUTHENTICATED (16)` |
| Authorization failure | `PERMISSION_DENIED (7)` |
| Resource exhausted (rate limit) | `RESOURCE_EXHAUSTED (8)` |
| Not found | `NOT_FOUND (5)` |
| Conflict / already exists | `ALREADY_EXISTS (6)` |
| Deadline exceeded | `DEADLINE_EXCEEDED (4)` |
| Internal failure | `INTERNAL (13)` |
| Not implemented | `UNIMPLEMENTED (12)` |
| Unavailable (transient) | `UNAVAILABLE (14)` |
| Cancelled by client | `CANCELLED (1)` |

Never use `OK (0)` for failures. Never use `UNKNOWN (2)` unless absolutely necessary; surface the actual code.

### 4. Observability

1. Export OpenTelemetry traces with `rpc.system = "grpc"`, `rpc.service`, `rpc.method`, `rpc.grpc.status_code`.
2. Export metrics: request rate, error rate (per status code), latency histogram, in-flight streams.
3. Export logs with trace correlation (`trace_id`, `span_id`).
4. Wire service-mesh access logs to a single sink.

### 5. Service mesh integration

1. Declare the service in the mesh's service registry.
2. Configure mutual TLS (mTLS) per `SERVICE_MESH_MTLS_ROLLOUT_PLAYBOOK.md`.
3. Set protocol detection timeout to 5 seconds.
4. Configure destination-level traffic policies (retries, timeouts, circuit breakers).
5. Validate `Health.Check` via the mesh probe.

### 6. Launch validation

1. Run integration tests against the staging deployment.
2. Confirm trace export, metric export, log export.
3. Confirm `Health.Check` returns `SERVING`.
4. Confirm trailer-only failure under simulated dependency outage.
5. Run a load test with the representative workload (request rate, payload size, mix).
6. Confirm error rate < 0.1% under steady state.

### 7. Documentation

1. Add a reference card under `docs/knowledge/reference/` (if the gRPC surface is reusable) or under `docs/knowledge/standards/` (if it is a policy).
2. Update the API catalog.
3. Document the on-call runbook.

## Rollback

Rollback decisions:

- p99 latency > 2x baseline for 15 minutes → revert.
- Error rate > 5% for 5 minutes → revert.
- Health probe returning `NOT_SERVING` > 1 minute → revert.

Rollback procedure:

1. Revert the deployment to the last-known-good image.
2. Page the on-call service owner.
3. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `GRPC_VERSION_GOVERNANCE.md`
- `SERVICE_MESH_MTLS_ROLLOUT_PLAYBOOK.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- gRPC status code reference: `https://grpc.io/docs/guides/status-codes/`
- gRPC health protocol: `https://github.com/grpc/grpc/blob/master/doc/health-checking.md`
