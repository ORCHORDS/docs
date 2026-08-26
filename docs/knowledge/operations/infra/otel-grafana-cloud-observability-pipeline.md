# OpenTelemetry to Grafana Cloud: End-to-End Observability Pipeline

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Traces land in one vendor, metrics in another, and logs in a third; engineers switch tabs during
incidents instead of correlating all three signals in a unified view driven by a single pipeline config.

## Context
Grafana Cloud's OTLP endpoint accepts traces (Tempo), metrics (Mimir), and logs (Loki) over a single
OTLP/gRPC or OTLP/HTTP connection. An OpenTelemetry Collector deployed as a Kubernetes DaemonSet or
a Cloudflare Tail Worker acts as the gateway — it enriches, batches, and fans out to Grafana Cloud
while also emitting to a local Prometheus scrape endpoint for low-latency alerting.
This approach avoids vendor SDK lock-in because all instrumentation targets the OTel SDK.

## Collector Configuration (Kubernetes DaemonSet)

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

  # Scrape kubelet and node metrics
  prometheus:
    config:
      scrape_configs:
        - job_name: kubelet
          kubernetes_sd_configs:
            - role: node
          scheme: https
          tls_config:
            ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
            insecure_skip_verify: true
          bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
          relabel_configs:
            - action: labelmap
              regex: __meta_kubernetes_node_label_(.+)
            - target_label: __address__
              replacement: kubernetes.default.svc:443
            - source_labels: [__meta_kubernetes_node_name]
              target_label: __metrics_path__
              replacement: /api/v1/nodes/$1/proxy/metrics

processors:
  batch:
    timeout: 5s
    send_batch_size: 1024

  memory_limiter:
    check_interval: 1s
    limit_percentage: 75
    spike_limit_percentage: 20

  resource:
    attributes:
      - action: insert
        key: deployment.environment
        value: ${env:DEPLOYMENT_ENV}
      - action: insert
        key: service.namespace
        value: ${env:K8S_NAMESPACE}

  # Drop high-cardinality health check spans
  filter/drop_health:
    error_mode: ignore
    traces:
      span:
        - 'attributes["http.route"] == "/healthz"'
        - 'attributes["http.route"] == "/readyz"'

exporters:
  otlphttp/grafana:
    endpoint: https://otlp-gateway-prod-us-central-0.grafana.net/otlp
    auth:
      authenticator: basicauth/grafana

  # Local Prometheus exposition for in-cluster alerting (no round-trip to cloud)
  prometheus:
    endpoint: "0.0.0.0:8889"
    resource_to_telemetry_conversion:
      enabled: true

extensions:
  basicauth/grafana:
    client_auth:
      username: ${env:GRAFANA_INSTANCE_ID}
      password: ${env:GRAFANA_API_KEY}
  health_check:
  pprof:

service:
  extensions: [basicauth/grafana, health_check, pprof]
  pipelines:
    traces:
      receivers:  [otlp]
      processors: [memory_limiter, resource, filter/drop_health, batch]
      exporters:  [otlphttp/grafana]
    metrics:
      receivers:  [otlp, prometheus]
      processors: [memory_limiter, resource, batch]
      exporters:  [otlphttp/grafana, prometheus]
    logs:
      receivers:  [otlp]
      processors: [memory_limiter, resource, batch]
      exporters:  [otlphttp/grafana]
```

## Kubernetes Deployment Manifest

```yaml
# otel-collector-daemonset.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-collector
  namespace: observability
spec:
  selector:
    matchLabels:
      app: otel-collector
  template:
    metadata:
      labels:
        app: otel-collector
    spec:
      serviceAccountName: otel-collector
      containers:
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:0.105.0
          args: ["--config=/conf/config.yaml"]
          env:
            - name: DEPLOYMENT_ENV
              value: production
            - name: K8S_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: GRAFANA_INSTANCE_ID
              valueFrom:
                secretKeyRef:
                  name: grafana-cloud-creds
                  key: instanceId
            - name: GRAFANA_API_KEY
              valueFrom:
                secretKeyRef:
                  name: grafana-cloud-creds
                  key: apiKey
          ports:
            - containerPort: 4317  # OTLP gRPC
            - containerPort: 4318  # OTLP HTTP
            - containerPort: 8889  # Prometheus metrics
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          volumeMounts:
            - name: config
              mountPath: /conf
      volumes:
        - name: config
          configMap:
            name: otel-collector-config
```

## TypeScript SDK Instrumentation (Cloudflare Workers)

```typescript
// src/instrumentation.ts
import {
  WebTracerProvider,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-web";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { Resource } from "@opentelemetry/resources";
import { SemanticResourceAttributes } from "@opentelemetry/semantic-conventions";

export function createProvider(env: Env): WebTracerProvider {
  const exporter = new OTLPTraceExporter({
    url: env.OTEL_EXPORTER_OTLP_ENDPOINT + "/v1/traces",
    headers: {
      Authorization: `Basic ${btoa(`${env.GRAFANA_INSTANCE_ID}:${env.GRAFANA_API_KEY}`)}`,
    },
  });

  const provider = new WebTracerProvider({
    resource: new Resource({


      "cloudflare.colo": "auto", // populated at runtime via cf.colo
    }),
  });

  provider.addSpanProcessor(new SimpleSpanProcessor(exporter));
  provider.register();
  return provider;
}
```

```typescript
// src/index.ts
import { trace, SpanStatusCode } from "@opentelemetry/api";
import { createProvider } from "./instrumentation";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const provider = createProvider(env);
    const tracer = trace.getTracer("api-worker", "1.0.0");

    return tracer.startActiveSpan("http.request", async (span) => {
      span.setAttribute("http.method", request.method);
      span.setAttribute("http.url", request.url);
      try {
        const response = await handleRequest(request, env);
        span.setAttribute("http.status_code", response.status);
        span.setStatus({ code: SpanStatusCode.OK });
        return response;
      } catch (err) {
        span.recordException(err as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw err;
      } finally {
        span.end();
        ctx.waitUntil(provider.forceFlush());
      }
    });
  },
};
```

## Grafana Cloud Alerting Rule (Mimir)

```yaml
# grafana/alerts/worker-errors.yaml
apiVersion: 1
groups:
  - name: worker-alerts
    rules:
      - alert: WorkerErrorRateHigh
        expr: |
          sum(rate(http_server_request_duration_seconds_count{
            service_name="api-worker",
            http_response_status_code=~"5.."
          }[5m])) /
          sum(rate(http_server_request_duration_seconds_count{
            service_name="api-worker"
          }[5m])) > 0.01
        for: 2m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Worker error rate above 1% for 2 minutes"
          runbook_url: "https://wiki.example.com/runbooks/worker-errors"
```

## Anti-patterns
- Sending traces directly from each service to Grafana Cloud without a Collector — you lose batching, enrichment, and the ability to swap exporters
- Using SDK-level filtering to drop spans before they reach the Collector — the Collector's `filter` processor is the right place
- Omitting `memory_limiter` processor — OOM-killed collectors drop all buffered telemetry
- Running one Collector per pod instead of one per node (DaemonSet) — inflates resource usage 10-100x
- Using `logging` exporter in production — it doubles log volume and leaks span payloads to stdout

## Gotchas
- Grafana Cloud's OTLP endpoint URL varies by region and instance; copy it from the Grafana Cloud portal under "OpenTelemetry" — do not hard-code the example URL
- `basicauth` extension in the Collector expects base64-encoded credentials in the `password` field only when using HTTP Basic; for token auth, the password IS the token
- Workers' `SimpleSpanProcessor` calls `forceFlush()` synchronously at the end of a request; use `ctx.waitUntil()` to prevent the runtime from terminating before the flush completes
- High-cardinality label dimensions (user IDs, UUIDs) in metrics will exhaust Mimir's series limit — use the `transform` processor to drop before export
- `filter/drop_health` uses OTTL syntax; test locally with `otelcol validate --config config.yaml`

## Verification
```bash
# Send a test trace to local Collector
curl -X POST http://localhost:4318/v1/traces \
  -H "Content-Type: application/json" \
  -d @test-trace.json

# Check Collector self-metrics
curl -s http://localhost:8889/metrics | grep otelcol_exporter_sent

# Query Grafana Cloud Tempo for recent traces
curl -s -u "$GRAFANA_INSTANCE_ID:$GRAFANA_API_KEY" \
  "https://tempo-prod-us-central-0.grafana.net/tempo/api/search?limit=5" \
  | jq '.traces[].rootServiceName'
```

## Related
- `/documentation/docs/policies/infra/opentelemetry-collector-config.md`
- `/documentation/docs/policies/infra/workers-opentelemetry-tail-workers.md`
- `/documentation/docs/policies/infra/grafana-dashboard-as-code.md`
- `/documentation/docs/policies/infra/monitoring-stack-2026.md`

## Sources
- https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/
- https://opentelemetry.io/docs/collector/configuration/
- https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/filterprocessor
- https://developers.cloudflare.com/workers/observability/logs/workers-trace-events-logpush/
