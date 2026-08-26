# RED and USE: The Two Metrics Frameworks You Always Need

RED and USE are the foundational frameworks for picking *which* metrics to
alert on. Without them you fall into the trap of monitoring everything and
understanding nothing.

- **RED** (Tom Wilkie) — for *request-driven* services (HTTP APIs, RPC).
  Rate, Errors, Duration.
- **USE** (Brendan Gregg) — for *resource* objects (CPU, disk, network,
  connection pools). Utilization, Saturation, Errors.

If you only have one of these per component you are flying half-blind.

## Symptom

- You get paged for high CPU utilization but the service is perfectly fine —
  the load is actually saturated on the database, not the CPU.
- An SLO is breached but you cannot tell whether it is because error rate
  rose, latency rose, or both — your dashboards conflate them.
- "The service is slow" and nobody knows whether to look at queue depth,
  thread pool, or request latency because there is no shared vocabulary.
- A resource shows 90% utilization but is not actually saturated (e.g. SSD
  I/O), causing false-positive alerts.
- Alerts fire on individual metrics without context (a 1-minute latency spike
  that has zero user impact because the error rate stayed flat).

## Gotchas

- **RED is for services, USE is for resources — don't mix them.** Applying
  RED to a database (rate of queries, errors, duration) is correct. Applying
  USE to an HTTP endpoint ("utilization of the endpoint") is meaningless.
  Endpoints do not have utilization in the resource sense.
- **Utilization alone is misleading for alerts.** A CPU at 99% with low
  run-queue saturation may be fine; a CPU at 60% with a saturated run queue
  is on fire. Always pair Utilization with Saturation. This is the #1 cause
  of useless "CPU high" pages.
- **Duration is a distribution, not a number.** p50 is useless for SLOs.
  Track p95 and p99 and alert on multi-window burn rate against the SLO
  threshold — single-threshold p99 alerts flapping is a classic failure.
- **Errors in RED should include protocol-level errors.** A 500 is obvious;
  a 200 with a stack trace in the body, or a gRPC `INTERNAL` code, or a
  GraphQL `errors` array are also errors. Count them or your error rate
  underreports.
- **Saturation is component-specific.** Use the right signal: CPU run-queue
  length, disk queue depth, network `tcp_retransmit_rate`, connection pool
  wait time, thread pool queue size. There is no universal saturation metric.
- **Rate must be per-deployment, not per-pod.** Aggregate across replicas;
  per-pod rate is noise. But always keep a per-pod series for spotting a
  single misbehaving instance via outlier detection.
- **RED maps directly to SLOs.** Availability = (1 - errors/rate) and latency
  = duration percentile. If your RED metrics are right, your SLO calculation
  is trivial. If they're wrong, your SLO is fiction.

## Example: RED dashboard panel layout (Prometheus)

```promql
# Rate — requests per second, by route
sum by (route) (rate(http_requests_total[5m]))

# Errors — error rate as a fraction of total
sum by (route) (rate(http_requests_total{status=~"5.."}[5m]))
  /
sum by (route) (rate(http_requests_total[5m]))

# Duration — p99 latency by route
histogram_quantile(0.99,
  sum by (route, le) (rate(http_request_duration_seconds_bucket[5m])))
```

## Example: USE for a Linux host

```promql
# CPU Utilization — 1 - idle fraction across all cores
1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m]))

# CPU Saturation — average run-queue length (load avg / core count)
node_load1 / on(instance) count by (instance) (node_cpu_seconds_total{mode="idle"})

# Disk Utilization — % time spent doing I/O
rate(node_disk_io_time_seconds_total[5m])

# Disk Saturation — average queue depth
rate(node_disk_io_time_weighted_seconds_total[5m])  # weighted = queue*io_time

# Network Errors — retransmits per second
rate(node_netstat_Tcp_RetransSegs[5m])
```

## Mapping every component to its framework

| Component          | Framework | Key metrics                                  |
|--------------------|-----------|----------------------------------------------|
| HTTP/gRPC API      | RED       | req/s, error%, p95/p99 latency               |
| Database           | Both      | RED (query) + USE (connections, I/O)         |
| Cache              | RED       | req/s, miss/error%, latency + hit rate       |
| Queue/Stream       | USE       | publish/consume rate, lag (saturation), DLQ  |
| Host/VM            | USE       | CPU, mem, disk, net utilization+saturation   |
| Connection pool    | USE       | utilization (in-use/max), wait time, leaks   |

## Verifying it works

- For every service you should be able to point at one RED panel set and one
  USE panel set per backing resource. Missing either is a blind spot.
- Each SLO should map to exactly one RED metric (error rate or latency) — if
  it doesn't, your SLO is unmeasurable.
- Alert fatigue should drop because saturation-aware alerts catch the real
  bottleneck instead of paging on util-only noise.
