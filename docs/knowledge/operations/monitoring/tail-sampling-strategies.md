# Tail Sampling Strategies for Distributed Tracing

When every request generates a span, distributed tracing backends drown in
data. Head sampling (drop 99% of traces at the source) is cheap but blind:
you sample away the exact slow/error traces you need. Tail sampling looks at
the *whole trace* after it completes and decides whether to keep it, so you
keep 100% of errors and slow requests while dropping the boring fast-OK ones.

## Symptom

- Tracing backend ingest costs are exploding but trace detail is useless.
- You keep the slow trace for the payment service but miss the upstream auth
  call that caused the delay because head sampling dropped the parent span.
- You only see "error" traces but never the full request path that led there.
- Jaeger/Tempo shows gaps in a trace where intermediate services were sampled
  out, making the trace un-followable.
- 99th-percentile latency SLO violations have no correlated trace to explain
  them.

## Gotchas

- **Tail sampling must happen AFTER the trace completes.** If you tail-sample
  at the application SDK level, each process only sees its own spans, not the
  whole trace. You need a centralized collector (OpenTelemetry Collector with
  the `tail_sampling` processor) that buffers spans by `trace_id` until the
  trace is complete or the `decision_wait` timer (default 30s) fires.
- **`decision_wait` vs. memory.** Longer wait = more complete traces but more
  memory held. A 30s wait on a 10k-span/s workload can hold GBs. Start at 10s
  for high-volume, 60s for batch/background workloads.
- **`num_traces` buffer limit is a silent cliff.** When the in-memory trace
  count exceeds this cap, the collector evicts oldest traces *before*
  evaluating them — your policy never sees them. Monitor the
  `num_traces_dropped` counter; if it grows, raise the limit or scale out
  collector replicas.
- **Sampling by error/slow is easy to get backwards.** The correct policy
  order is: keep errors → keep slow → keep a small % of the rest. Reversing
  this means the slow/error rules evaluate against a pre-diluted set.
- **Always sample new-version deploy traffic.** A `version` tag policy that
  keeps 100% of traces for the canary revision prevents the classic "we
  deployed and now it's slow but we can't see why" gap.
- **Tail sampling does not reduce SDK overhead.** Spans are still created,
  serialized, and exported to the collector regardless. If SDK CPU/allocation
  cost is the problem, also add ratio head sampling *before* tail sampling,
  or use OpenTelemetry's span summarization.
- **Async/background spans break trace completion detection.** Traces that
  include fan-out to queues or scheduled jobs may never "complete" within
  `decision_wait`. Either exclude those traces from tail sampling or increase
  the wait for traces with specific baggage tags.

## Example: OpenTelemetry Collector tail_sampling processor

```yaml
# otel-collector-config.yaml
processors:
  tail_sampling:
    decision_wait: 30s
    num_traces: 100000        # in-memory trace buffer
    expected_new_traces_per_sec: 1000
    policies:
      # 1. Keep ALL traces with any error span
      - name: errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      # 2. Keep ALL traces slower than 500ms
      - name: slow
        type: latency
        latency:
          threshold_ms: 500
      # 3. Keep 100% of canary-revision traffic
      - name: canary
        type: string_attribute
        string_attribute:
          key: service.version
          values: ["canary"]
      # 4. Keep 5% of everything else for baseline visibility
      - name: baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 5

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [tail_sampling]
      exporters: [otlp/tempo]
```

## Verifying it works

- Check `otelcol_processor_tail_sampling_count_traces_sampled` — the
  `policy` label tells you which rule kept each trace.
- Confirm error traces are ~100% retained: the ratio of sampled-error traces
  to total emitted-error traces should be near 1.0.
- If you added probabilistic head sampling upstream, multiply your head %
  by tail % to get the real retained rate and make sure it is non-zero for
  your critical traffic.
