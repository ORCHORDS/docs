# Kubernetes KEDA Autoscaling with Cloudflare Queue Consumers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Kubernetes-based worker fleet processes messages from Cloudflare Queues but scales only on CPU, leaving messages backed up for minutes during traffic spikes while idle replicas waste compute during quiet periods. Standard HPA cannot see the Cloudflare Queue backlog depth, so the autoscaler reacts too late and over-provisions during sustained load. Operators want scale-to-zero during off-hours and burst-to-N on queue depth threshold, driven by the actual message backlog rather than CPU proxy metrics.

## Context

Cloudflare Queues is a pull-based message queue built into the Workers platform: producers enqueue messages via `env.MY_QUEUE.send()` inside a Worker, and consumers are registered Workers that Cloudflare invokes in batches on a configurable interval. However, some processing workloads are too resource-intensive or stateful for Workers' CPU and memory limits — they belong on Kubernetes. The pattern here is a hybrid architecture: a Cloudflare Worker acts as the queue consumer, pulls batches, and forwards them over HTTP or gRPC to a Kubernetes Deployment (the actual processor). KEDA autoscales the Deployment based on a custom Prometheus metric (queue consumer lag) or via KEDA's HTTP scaler watching the Worker's forwarding rate. example project uses this pattern for audio transcription jobs, large file processing, and React Native OTA bundle generation that exceeds Workers' 128 MB memory ceiling.

## Architecture Overview

```
Mobile App / Next.js
       │  send()
       ▼
┌──────────────────┐
│  Cloudflare Queue│ (producer: Workers binding)
│  example project-jobs-queue │
└────────┬─────────┘
         │ batch pull (Cloudflare invokes consumer Worker)
         ▼
┌──────────────────────────┐
│ Consumer Worker          │
│ (queue-consumer.ts)      │  forwards batch over mTLS HTTP
│ retries, DLQ handling    │
└────────┬─────────────────┘
         │  POST /process-batch
         ▼
┌──────────────────────────────────────────────────────┐
│  Kubernetes Deployment: example project-job-processor           │
│  KEDA ScaledObject watching Prometheus queue_lag_ms  │
│  minReplicas: 0  maxReplicas: 20                     │
└──────────────────────────────────────────────────────┘
```

## Cloudflare Queue Producer (Worker)

```typescript
// src/producer.ts — enqueues jobs from the Next.js API layer
export interface Env {
  JOBS_QUEUE: Queue<JobMessage>;
}

interface JobMessage {
  type: 'transcribe' | 'bundle-ota' | 'resize-image';
  payload: Record<string, unknown>;
  traceId: string;
  enqueuedAt: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.json<JobMessage>();
    await env.JOBS_QUEUE.send({
      ...body,
      enqueuedAt: new Date().toISOString(),
    }, {
      contentType: 'json',
      delaySeconds: 0,
    });

    return Response.json({ queued: true, traceId: body.traceId });
  },
} satisfies ExportedHandler<Env>;
```

## Cloudflare Queue Consumer Worker (Batch Forwarding)

```typescript
// src/consumer.ts — receives queue batches, forwards to K8s processor
export interface Env {
  JOBS_QUEUE: Queue;
  PROCESSOR_URL: string;   // https://processor.internal.example project.example.com
  PROCESSOR_TOKEN: string; // secret binding
  QUEUE_METRICS_KV: KVNamespace; // stores lag metrics for Prometheus scraping
}

export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    const messages = batch.messages.map(m => ({
      id: m.id,
      body: m.body,
      timestamp: m.timestamp.toISOString(),
    }));

    const lagMs = Date.now() - Math.min(
      ...batch.messages.map(m => m.timestamp.getTime())
    );

    // Write lag metric to KV for Prometheus scraping
    await env.QUEUE_METRICS_KV.put(
      'queue_consumer_lag_ms',
      String(lagMs),
      { expirationTtl: 300 }
    );

    try {
      const resp = await fetch(`${env.PROCESSOR_URL}/process-batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${env.PROCESSOR_TOKEN}`,
          'X-Batch-Size': String(messages.length),
          'X-Queue-Lag-Ms': String(lagMs),
        },
        body: JSON.stringify({ messages }),
        signal: AbortSignal.timeout(25000), // Workers 30s CPU limit
      });

      if (!resp.ok) {
        // Retry the entire batch on 5xx
        batch.retryAll({ delaySeconds: 30 });
        return;
      }

      // Ack individual messages on success
      for (const msg of batch.messages) {
        msg.ack();
      }
    } catch (err) {
      // Network error — retry with backoff
      batch.retryAll({ delaySeconds: 60 });
    }
  },
} satisfies ExportedHandler<Env>;
```

Queue binding in `wrangler.toml`:

```toml
name = "example project-queue-consumer"
main = "src/consumer.ts"
compatibility_date = "2026-08-01"

[[queues.consumers]]
queue = "example project-jobs-queue"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "example project-jobs-dlq"
retry_delay = 60

[[kv_namespaces]]
binding = "QUEUE_METRICS_KV"
id = "abcdef1234567890abcdef1234567890"
```

## Prometheus Metrics Exporter (Kubernetes sidecar)

A small exporter sidecar reads the lag metric from Cloudflare KV and exposes it for KEDA's Prometheus scaler:

```python
# metrics-exporter/main.py
import os, time, requests
from prometheus_client import start_http_server, Gauge

LAG_GAUGE = Gauge('cloudflare_queue_lag_ms',
                  'Cloudflare Queue consumer lag in milliseconds',
                  ['queue_name'])

CF_API_TOKEN  = os.environ['CF_API_TOKEN']
CF_ACCOUNT_ID = os.environ['CF_ACCOUNT_ID']
KV_NAMESPACE  = os.environ['KV_NAMESPACE_ID']
QUEUE_NAME    = os.environ.get('QUEUE_NAME', 'example project-jobs-queue')
SCRAPE_INTERVAL = int(os.environ.get('SCRAPE_INTERVAL_S', '10'))

def fetch_lag():
    url = (f'https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}'
           f'/storage/kv/namespaces/{KV_NAMESPACE}/values/queue_consumer_lag_ms')
    r = requests.get(url, headers={'Authorization': f'Bearer {CF_API_TOKEN}'}, timeout=5)
    if r.status_code == 200:
        return float(r.text)
    return 0.0

if __name__ == '__main__':
    start_http_server(8080)
    while True:
        LAG_GAUGE.labels(queue_name=QUEUE_NAME).set(fetch_lag())
        time.sleep(SCRAPE_INTERVAL)
```

## Kubernetes Deployment and KEDA ScaledObject

```yaml
# k8s/job-processor-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: example project-job-processor
  namespace: example project-production
spec:
  replicas: 1   # KEDA manages replica count; set initial value
  selector:
    matchLabels:
      app: example project-job-processor
  template:
    metadata:
      labels:
        app: example project-job-processor
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
    spec:
      containers:
        - name: processor
          image: ghcr.io/example-org/example-repo:latest
          ports:
            - containerPort: 3000
          env:
            - name: PROCESSOR_TOKEN
              valueFrom:
                secretKeyRef:
                  name: processor-secrets
                  key: token
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "2Gi"
          readinessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 5

        - name: metrics-exporter
          image: ghcr.io/example-org/example-repo:latest
          ports:
            - containerPort: 8080
          env:
            - name: CF_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: cloudflare-secrets
                  key: api-token
            - name: CF_ACCOUNT_ID
              valueFrom:
                secretKeyRef:
                  name: cloudflare-secrets
                  key: account-id
            - name: KV_NAMESPACE_ID
              value: "abcdef1234567890abcdef1234567890"
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
```

```yaml
# k8s/keda-scaled-object.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: example project-job-processor-scaler
  namespace: example project-production
spec:
  scaleTargetRef:
    name: example project-job-processor
  pollingInterval: 15         # Check metrics every 15 seconds
  cooldownPeriod: 120         # Wait 2 min after last scale event before scaling down
  minReplicaCount: 0          # Scale to zero when queue is empty
  maxReplicaCount: 20
  fallback:
    failureThreshold: 3       # Keep current replicas if metric fetch fails 3x
    replicas: 2

  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring.svc.cluster.local:9090
        metricName: cloudflare_queue_lag_ms
        threshold: "5000"     # Scale up when lag exceeds 5 seconds
        query: |
          cloudflare_queue_lag_ms{queue_name="example project-jobs-queue"}
        activationThreshold: "1000"  # Activate from 0 replicas when lag > 1s

    # Secondary trigger: HTTP request rate to the processor
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring.svc.cluster.local:9090
        metricName: http_requests_in_flight
        threshold: "50"
        query: |
          sum(rate(http_requests_total{job="example project-job-processor"}[1m])) * 60
```

## Dead Letter Queue Handling

```typescript
// src/dlq-consumer.ts — alerts on dead-lettered messages
export interface Env {
  JOBS_DLQ: Queue;
  ALERT_WEBHOOK: string;
}

export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    const failed = batch.messages.map(m => ({
      id: m.id,
      body: m.body,
      retries: (m as any).attempts ?? 'unknown',
    }));

    await fetch(env.ALERT_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: `Dead-lettered ${failed.length} messages from example project-jobs-queue`,
        messages: failed,
      }),
    });

    // Ack DLQ messages to prevent infinite re-delivery
    for (const msg of batch.messages) {
      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;
```

## Mobile vs Desktop Considerations

example project's mobile (React Native) and desktop (Next.js) clients enqueue jobs through the same Worker API. Key differences:

- **Mobile**: Audio transcription and image resize jobs are enqueued from the React Native app via the producer Worker endpoint; mobile clients poll a status KV key for job completion rather than holding a WebSocket open
- **Desktop**: Next.js server actions enqueue OTA bundle generation jobs; the status is streamed back via Server-Sent Events from a polling Worker
- **Queue depth**: Mobile users tend to generate burst traffic during morning commutes (UTC+4 peaks for the primary market); KEDA `cooldownPeriod: 120` prevents thrashing during these predictable bursts
- **Latency SLA**: Mobile users tolerate 30-60 s for async jobs; configure `max_batch_timeout: 5` (Worker pulls every 5 s) and KEDA `pollingInterval: 15` for a combined worst-case latency of ~20 s from enqueue to K8s pod startup

## Anti-patterns

- Polling the Cloudflare Queue backlog depth via the REST API in a tight loop — the API has rate limits and does not expose queue depth directly; use consumer lag (time from enqueue to consumption) as the scaling metric instead
- Setting `minReplicaCount: 0` without an `activationThreshold` — KEDA cannot scale from 0 if the metric query returns no data; ensure the exporter always returns 0 (not empty) when the queue is idle
- Using Workers as direct processors for jobs exceeding 128 MB memory or 30 s CPU — offload to K8s; Workers are the routing and acknowledgment layer only
- Ignoring the `fallback` stanza in ScaledObject — if the Prometheus exporter sidecar crashes, KEDA defaults to 0 replicas, processing stops silently
- Acking messages in the Worker before the K8s processor confirms success — on a 5xx from the processor, messages are lost; always check the response before `msg.ack()`

## Gotchas

- Cloudflare Queues does not expose queue depth via a public API in 2026 — the only reliable lag signal is the difference between message `timestamp` and consumption time, computed inside the consumer Worker
- KEDA's Prometheus scaler requires the metric to exist in Prometheus before the ScaledObject can activate scale-from-zero; seed the metric with a 0 value at startup
- Workers on the `standard` usage model have a 10 ms CPU time limit per request; the queue consumer runs under the `queue` handler which has a 30 s wall-clock limit but a separate CPU budget — check `cpu_time_ms` in Logpush
- The `retry_delay` in `wrangler.toml` sets the minimum delay before retry; actual retry timing is controlled by Cloudflare and may be longer during platform load
- KEDA `ScaledObject` owns the HPA object — do not create a separate HPA for the same Deployment; the conflict causes undefined scaling behavior

## Verification

```bash
# Check KEDA operator is running
kubectl -n keda get pods
kubectl -n example project-production get scaledobject example project-job-processor-scaler

# Inspect current replica count and scaler status
kubectl -n example project-production describe scaledobject example project-job-processor-scaler

# Check HPA created by KEDA
kubectl -n example project-production get hpa

# Manually trigger a test message to exercise the pipeline
wrangler queue send example project-jobs-queue '{"type":"transcribe","payload":{"url":"gs://test"},"traceId":"test-001","enqueuedAt":""}'

# Watch processor Deployment scale up
kubectl -n example project-production get deployment example project-job-processor -w

# Read lag metric from KV directly
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces/$KV_NS/values/queue_consumer_lag_ms" \
  -H "Authorization: Bearer $CF_API_TOKEN"
```

## Related

- `documentation/docs/policies/infra/kubernetes-keda-event-driven-autoscaling.md`
- `documentation/docs/policies/infra/karpenter-keda-autoscaling.md`
- `documentation/docs/policies/infra/cloudflare-workers-limits-resource-planning.md`
- `documentation/docs/policies/infra/wrangler-toml-multi-environment-config.md`
- `documentation/docs/policies/infra/kubernetes-autoscaling-hpa-keda.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/javascript-apis/
- https://keda.sh/docs/latest/scalers/prometheus/
- https://keda.sh/docs/latest/concepts/scaling-deployments/#scaledobject-spec
- https://developers.cloudflare.com/queues/configuration/configure-queues/
