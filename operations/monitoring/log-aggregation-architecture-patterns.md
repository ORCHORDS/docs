# Log Aggregation Architecture Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your logs are scattered across dozens of services, each writing to local
files or stdout. Debugging a cross-service issue requires SSH-ing into
multiple hosts and grepping individual log files. There is no centralized
view, no correlation between services, and no retention policy.

## Context

Log aggregation collects logs from all services, ships them to a central
store, and makes them searchable. The architecture choice — push vs. pull,
agent vs. agentless, fan-in vs. fan-out — determines cost, latency, and
reliability. In 2026, the dominant patterns use an OpenTelemetry Collector
or vector/fluentbit as the edge agent, with Loki, Elasticsearch, or a SaaS
backend (Datadog, Axiom) as the store.

## Architecture patterns

### 1. Agent-per-node (most common)

```
Service → stdout → Container runtime → Log agent (per node)
                                              ↓
                                    Central aggregator / store
```

A log agent (Fluent Bit, OTel Collector, Vector) runs on every node, reads
container stdout/stderr, enriches with metadata (pod name, namespace,
labels), and ships to the central store.

- **Best for:** Kubernetes clusters, containerized workloads.
- **Tools:** Fluent Bit (lightweight, C), OTel Collector (standard),
  Vector (Rust, high performance).

### 2. Sidecar-per-pod

```
App container → shared volume → Sidecar agent → Central store
```

A sidecar container in each pod reads log files from a shared volume.

- **Best for:** applications that write structured logs to files (not
  stdout), multi-container pods with different log formats.
- **Tradeoff:** higher resource overhead (one agent per pod vs. per node).

### 3. Direct push (agentless)

```
Service → HTTP/gRPC → Central store API
```

The application ships logs directly via an SDK or HTTP client.

- **Best for:** serverless (Lambda, Workers), edge functions where no agent
  can run.
- **Tradeoff:** couples the application to the log backend; no local
  buffering on failure.

### 4. Edge aggregation (fan-in → fan-out)

```
Services → Node agent → Edge aggregator (per AZ/region)
                              ↓
                    Central store (cross-region)
```

An intermediate aggregation tier reduces egress costs and provides local
buffering. The edge aggregator batches, compresses, and filters before
forwarding.

- **Best for:** multi-region deployments, high-volume workloads where cross-
  region egress is expensive.
- **Tools:** Vector (aggregator mode), OTel Collector (gateway deployment).

## Pipeline design

```
Source → Collection → Enrichment → Routing → Storage → Query
```

| Stage | What happens | Tools |
|---|---|---|
| **Collection** | Read from stdout, files, syslog, or API | Fluent Bit, OTel Collector, Vector |
| **Enrichment** | Add metadata: pod, namespace, node, trace ID, service name | Agent-side transforms |
| **Filtering** | Drop debug logs in production, redact PII, sample high-volume paths | Vector VRL, Fluent Bit filters, OTel processors |
| **Routing** | Send different log streams to different backends (errors → Elasticsearch, debug → Loki, audit → S3) | Multi-output configuration |
| **Storage** | Index and retain | Loki, Elasticsearch, Datadog, Axiom, S3 (cold) |
| **Query** | Search, filter, aggregate | Grafana (Loki), Kibana (ES), Datadog UI |

## Backpressure handling

When the central store is slow or down, logs queue in the agent. Without
backpressure handling, agents consume all available memory and crash.

- **Disk buffer** — Fluent Bit and Vector support disk-based buffering.
  Configure `storage.type filesystem` (Fluent Bit) or `buffer.type disk`
  (Vector).
- **Drop oldest** — when the buffer is full, drop the oldest logs (not the
  newest). Recent logs are more valuable for debugging.
- **Circuit breaker** — if the backend is down for > N minutes, stop
  buffering and drop. Alert on the circuit breaker state.

## Anti-patterns

- **Logging everything at DEBUG in production** — generates massive volume,
  increases cost, and makes searching harder. Use INFO as the default;
  enable DEBUG per-service via feature flag for debugging.
- **Unstructured logs** — `console.log("user " + id + " failed")` is
  unsearchable. Use structured JSON logging: `{"user_id": "123", "event":
  "login_failed", "reason": "invalid_password"}`.
- **No log correlation** — without a shared trace ID or request ID across
  services, correlating logs for a single request is impossible. Propagate
  `trace_id` and `span_id` in every log line.
- **Sending all logs to the most expensive tier** — route debug/info logs
  to cheap storage (Loki, S3) and error/audit logs to the queryable tier.
- **No retention policy** — unbounded retention fills storage. Set 7-day
  hot, 30-day warm, 90-day cold as a starting point. Compliance may require
  longer audit log retention.

## Gotchas

- **Multi-line log parsing** — stack traces span multiple lines. Configure
  multi-line parsers (Fluent Bit `multiline.parser`, Docker `max-size`
  with `json-file` driver).
- **Timestamp parsing** — mismatched timestamp formats cause ordering issues.
  Standardize on RFC 3339 (`2026-08-16T12:00:00Z`) across all services.
- **Label cardinality (Loki)** — Loki indexes by labels, not full text. High-
  cardinality labels (user ID, request ID) as Loki labels destroy
  performance. Use structured metadata or log line content for high-
  cardinality fields.
- **Egress costs** — shipping logs cross-region or to a SaaS vendor incurs
  network egress charges. Compress and filter at the edge.
- **PII in logs** — scrub PII before shipping to centralized logging. Use
  agent-side transforms, not post-hoc deletion.

## Verification

- Query a recent request by trace ID and verify logs from all involved
  services appear in the central store.
- Verify log latency: time from log emission to queryability should be < 30s
  for hot-tier logs.
- Test backpressure: stop the log backend and verify agents buffer without
  crashing.
- Verify PII redaction rules are applied before logs leave the agent.

## Related

- `documentation/categories/monitoring/log-structured-logging.md`
- `documentation/categories/monitoring/log-correlation-ids.md`
- `documentation/categories/monitoring/loki-log-labels.md`
- `documentation/categories/monitoring/opentelemetry-collector-pipelines.md`
- `documentation/categories/monitoring/log-security-masking.md`

## Source URLs (verified 2026-08-16)

- OpenTelemetry Collector documentation — https://opentelemetry.io/docs/collector/
- Vector documentation — https://vector.dev/docs/
- Fluent Bit documentation — https://docs.fluentbit.io/
- Grafana Loki documentation — https://grafana.com/docs/loki/latest/
