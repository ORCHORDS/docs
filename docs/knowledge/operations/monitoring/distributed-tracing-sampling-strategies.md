# Distributed Tracing Sampling Strategies — Head-Based, Tail-Based, and Adaptive Sampling

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your distributed tracing backend ingests 200 GB/day of span data at
a cost of $15,000/month. Setting sampling to 10% reduces cost but
you lose visibility into errors — the one failing request out of
10,000 gets dropped by the sampler. Your SRE team wants 100%
capture of error traces and all traces exceeding the P99 latency
threshold, while keeping baseline sampling at 5%. Head-based
sampling cannot make this decision because it does not know the
trace outcome at the point of the decision.

## Context

Distributed tracing sampling has two fundamental approaches:
head-based (decide at trace creation, before outcome is known) and
tail-based (buffer complete traces, then decide based on outcome).
Head-based sampling is cheap and stateless but blind to trace
outcomes. Tail-based sampling captures all interesting traces but
requires stateful infrastructure at the OpenTelemetry Collector
layer. The recommended 2026 approach layers both — head-based for
coarse volume reduction (5-20% baseline) with tail-based policies
at the Collector for guaranteed capture of errors, slow traces,
and specific attributes. Emerging research (2025) proposes span-
level sampling using code-knowledge signals for finer granularity.

## Head-based sampling

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# Sample 5% of traces — deterministic from trace ID
sampler = TraceIdRatioBased(0.05)
provider = TracerProvider(sampler=sampler)
```

```
Head-based sampling types:

  Sampler                    Behavior
  ──────────────────────────────────────────────────────────
  always_on                  100% (dev/staging only)
  always_off                 Drop everything
  traceidratio               Hash-based percentage of traces
  parentbased_traceidratio   Respect parent decision, ratio
                             for root spans only
  rate_limiting              Cap traces/second (token bucket)

  Consistent Probability: derives decision deterministically
  from trace ID + percentage. All services agree on the same
  decision for a given trace without coordination.

  ParentBased wraps a root sampler and delegates:
    → Remote parent sampled → sample
    → Remote parent not sampled → don't sample
    → No parent (root) → use configured sampler
```

```bash
# Environment variable configuration
export OTEL_TRACES_SAMPLER="parentbased_traceidratio"
export OTEL_TRACES_SAMPLER_ARG="0.05"
```

## Tail-based sampling (OpenTelemetry Collector)

```yaml
# collector-config.yaml
processors:
  tail_sampling:
    decision_wait: 30s
    num_traces: 100000
    expected_new_traces_per_sec: 1000
    decision_cache:
      sampled_cache_size: 100000
      non_sampled_cache_size: 100000
    policies:
      # Keep ALL error traces
      - name: errors-always
        type: status_code
        status_code:
          status_codes: [ERROR]

      # Keep traces with latency > 5 seconds
      - name: slow-traces
        type: latency
        latency:
          threshold_ms: 5000

      # Keep traces with specific attributes
      - name: vip-customers
        type: string_attribute
        string_attribute:
          key: customer.tier
          values: [enterprise, vip]

      # Rate-limit baseline traces
      - name: rate-limited-baseline
        type: rate_limiting
        rate_limiting:
          spans_per_second: 100

      # Probabilistic catch-all (MUST be last)
      - name: baseline-sample
        type: probabilistic
        probabilistic:
          sampling_percentage: 10
```

```
Tail-based sampling flow:

  1. All services export 100% of spans to Collector
  2. Collector buffers spans, groups by trace ID
  3. After decision_wait (e.g., 30s), evaluates complete trace
  4. Applies policies in order — first match wins
  5. Keeps matched traces, drops the rest

  Available policy types:
    always_sample, latency, numeric_attribute, probabilistic,
    status_code, string_attribute, rate_limiting, span_count,
    boolean_attribute, ottl_condition, and, not, drop, composite

  Policies evaluate in order — first match wins.
  Put targeted policies first, catch-all last.
```

## Scaling tail sampling

```
Challenge: spans for the same trace may arrive at different
Collector instances. Tail sampling needs all spans together.

Solution: trace-ID-consistent load balancing

  Service → Load Balancer (hash on trace ID)
         → Collector Instance A (traces 0-33%)
         → Collector Instance B (traces 34-66%)
         → Collector Instance C (traces 67-100%)

  Use the loadbalancing exporter in a first-tier Collector:

  exporters:
    loadbalancing:
      protocol:
        otlp:
          endpoint: collector-pool:4317
      routing_key: traceID
      resolver:
        dns:
          hostname: collector-pool
```

## Adaptive sampling

```
Dynamically adjusts rate based on live signals:

  → Traffic volume: reduce rate during peaks
  → System load: reduce when CPU/memory pressure rises
  → Backend capacity: match ingestion limits

  Jaeger remote sampler: pulls strategies from backend
    export OTEL_TRACES_SAMPLER="jaeger_remote"
    export OTEL_TRACES_SAMPLER_ARG="endpoint=http://jaeger:14268"

  Backend periodically computes optimal rates and pushes to SDKs.
```

## Anti-patterns

- **Relying only on head-based sampling for error capture** —
  head sampling is blind to trace outcomes. Errors, slow traces,
  and SLA violations are structurally missed at the same rate as
  everything else.
- **Ordering tail sampling policies wrong** — since first match
  wins, a broad probabilistic policy placed first short-circuits
  targeted error and latency policies. Always put targeted
  policies first and the catch-all last.
- **`always_on` in production** — a 1000 RPS service with 10
  spans per request generates 36 million spans per hour. Use
  `parentbased_traceidratio` with an appropriate percentage.
- **Not wrapping samplers in ParentBased** — applying a fresh
  probabilistic sampler without ParentBased causes inconsistent
  decisions where a child span is dropped independently of its
  parent, breaking trace completeness.

## Gotchas

- **`decision_wait` too short** — traces evaluated before all
  spans arrive (especially in async or fan-out architectures)
  show up as incomplete. Start at 30 seconds, tune up for
  async workloads.
- **Memory pressure from `num_traces`** — governs in-memory
  buffer size. Undersizing causes traces to be evicted before
  all spans arrive. Monitor Collector memory usage and tune
  `num_traces` and `expected_new_traces_per_sec` accordingly.
- **Single Collector instance** — without trace-ID-consistent
  load balancing, spans for the same trace land on different
  instances, breaking tail-based grouping entirely.
- **Tail sampling adds export latency** — the `decision_wait`
  period delays span export to the backend. This is acceptable
  for observability but means real-time dashboards lag by the
  wait duration.

## Verification

- Head-based sampling configured with `parentbased_traceidratio`.
- Tail sampling policies capture 100% of error and slow traces.
- Policy order: targeted policies first, probabilistic catch-all last.
- Trace-ID-consistent load balancing across Collector instances.
- Collector memory monitored and `num_traces` tuned appropriately.
- Sampling rates reviewed quarterly against cost and coverage goals.

## Related

- `documentation/docs/policies/monitoring/opentelemetry-collector-pipeline.md`
- `documentation/docs/policies/devtools/opentelemetry-sdk-instrumentation-tracing.md`
- `documentation/docs/policies/monitoring/slo-error-budget-burn-rate.md`

## Source URLs (verified 2026-08-16)

- Sampling Concepts (OpenTelemetry) — https://opentelemetry.io/docs/concepts/sampling/
- Tail Sampling Processor (opentelemetry-collector-contrib) — https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md
- OpenTelemetry Sampling Update 2025 — https://opentelemetry.io/blog/2025/sampling-milestones/
- Tail Sampling (Grafana OpenTelemetry Docs) — https://grafana.com/docs/opentelemetry/collector/sampling/tail/
