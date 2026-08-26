# OpenTelemetry Collector configuration

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Spans from a Cloudflare Worker arrive at the backend inconsistently.
Some are dropped during traffic spikes, PII appears in attribute
values, health-check spans dominate trace volume, and the monthly
ingestion bill doubled after adding two services. There is no single
place to apply sampling, redaction, or batching before data leaves
the edge.

## Context

The OpenTelemetry Collector receives, transforms, and exports traces,
metrics, and logs through configurable pipelines: receivers feed
processors, processors feed exporters. The Collector is the correct
place for tail-based sampling, PII redaction, and batching — concerns
that do not belong in application code. Cloudflare Workers cannot
run a sidecar; the Worker sends OTLP/HTTP to a Collector gateway
deployed on Cloud Run or Fly.io. The gateway then fans out to
multiple backends and applies all pipeline controls centrally.

## Pipeline configuration

```yaml
# otel-collector-config.yaml — annotated production baseline
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:           # always first — prevents OOM
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128

  attributes:               # PII redaction
    actions:
      - {key: user.email,              action: delete}
      - {key: http.request.header.authorization, action: delete}
      - {key: db.statement,            action: hash}

  filter:                   # drop health spans before billing
    traces:
      span:
        - 'attributes["http.route"] == "/health"'
        - 'attributes["http.route"] == "/ready"'

  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    policies:
      - {name: errors-always, type: status_code,
         status_code: {status_codes: [ERROR]}}
      - {name: slow-traces, type: latency,
         latency: {threshold_ms: 2000}}
      - {name: sample-rest, type: probabilistic,
         probabilistic: {sampling_percentage: 5}}

  batch:                    # always last before exporters
    send_batch_size: 1024
    timeout: 5s

exporters:
  otlphttp/primary:
    endpoint: https://ingest.grafana.com/otlp
    headers: {Authorization: "Basic ${env:GRAFANA_TOKEN}"}

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors:
        [memory_limiter, attributes, filter, tail_sampling, batch]
      exporters: [otlphttp/primary]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, filter, batch]
      exporters: [otlphttp/primary]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, attributes, batch]
      exporters: [otlphttp/primary]
```

Processor order is mandatory: `memory_limiter` first, `batch` last.
Placing `batch` before `tail_sampling` breaks sampling because the
sampler needs unbatched spans to correlate trace IDs.

## Tail-based sampling

Head sampling discards error traces probabilistically — the traces
most worth keeping. Tail sampling buffers all spans of a trace
before deciding, enabling 100 % retention of errors and slow traces.

Tail sampling requires all spans of a trace on one Collector
instance. In multi-Collector deployments, add a `loadbalancing`
exporter at the agent tier to route by `traceId` before the gateway:

```yaml
exporters:
  loadbalancing:
    protocol: {otlp: {tls: {insecure: true}}}
    resolver:
      static:
        hostnames:
          - gateway-0.internal:4317
          - gateway-1.internal:4317
```

## Attribute redaction for PII and Workers OTLP

The `attributes` processor (shown in the pipeline above) deletes or
hashes sensitive fields. Use the `transform` processor for regex
masking with OTTL statements such as `replace_pattern` (to redact
card numbers) and `truncate_all(attributes, 512)` (to cap size).
Maintain a documented field list and review it at each onboarding.

Workers cannot host a sidecar; the OTel JS SDK sends OTLP/HTTP
directly to the Collector gateway using `OTLPTraceExporter` pointed
at `https://otel-gateway.example.com/v1/traces`. Workers must never
bypass the gateway and write to storage backends directly — all
pipeline controls (redaction, sampling, batching) live in the
gateway Collector.

## Collector vs agent sidecar

| Dimension          | Gateway Collector    | Agent sidecar        |
|--------------------|----------------------|----------------------|
| Tail sampling      | Feasible             | Impractical (split)  |
| Workers compatible | Yes (HTTP target)    | No (no process)      |
| Resource overhead  | Shared, lower total  | Per-instance         |
| Failure blast      | Single point of risk | Isolated per node    |

For Workers stacks: gateway-only Collector on Cloud Run or Fly.io.
For Kubernetes: agent DaemonSet for node metadata, gateway
Deployment for tail sampling and multi-backend routing.

## Anti-patterns

- **No `memory_limiter`** — unbounded memory under load causes OOM
  kills and drops all in-flight telemetry.
- **Tail sampling at the agent** — agents see partial traces;
  decisions made there are effectively head sampling.
- **Redacting PII in application code only** — new fields get added;
  the Collector layer is the defense-in-depth backstop.
- **Exporting unfiltered health-check spans** — probes fire every
  10–30 s per instance and dominate volume and cost.

## Gotchas

- `decision_wait` must exceed the longest trace duration in the
  system. A 10 s wait drops spans from slow DB calls.
- The `contrib` distribution is required for vendor exporters
  (Datadog, Loki, Kafka); `core` includes only OTLP and Prometheus.
- Config hot-reload via SIGHUP does not apply receiver endpoint
  changes — those require a full process restart.
- `batch` flushes on whichever condition is met first:
  `send_batch_size` or `timeout`.

## Verification

- `memory_limiter` is the first processor in every pipeline.
- Health-check spans are absent from the storage backend after a
  10-minute soak test.
- Tail sampling retains 100 % of spans with ERROR status code.
- No `user.email` or `authorization` attribute appears in exported
  spans or log records.
- Collector CPU and memory are monitored with alerts at 80 % limit.

## Related

- `documentation/docs/policies/monitoring/opentelemetry-collector-pipelines.md`
- `documentation/docs/policies/monitoring/tail-sampling-strategies.md`
- `documentation/docs/policies/monitoring/otlp-export-protocol-selection.md`
- `documentation/docs/policies/monitoring/log-security-masking.md`
- `documentation/docs/policies/monitoring/observability-cost-control.md`

## Source URLs (verified 2026-08-17)

- OTel Collector configuration reference —
  https://opentelemetry.io/docs/collector/configuration/
- Tail sampling processor —
  https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor
- Transform processor (OTTL) —
  https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor
- otel-cf-workers (Cloudflare Workers OTel SDK) —
  https://github.com/evanderkoogh/otel-cf-workers
