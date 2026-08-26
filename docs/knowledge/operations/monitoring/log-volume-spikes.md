# Log Volume Spikes and Cardinality Explosions

A sudden 10x spike in log ingest is the most expensive monitoring failure
mode. It costs real money (Datadog/Loki/CloudWatch bill by GB or by event),
saturates the ingest pipeline causing legitimate logs to drop, and masks the
actual incident in noise. The cause is almost always one of three things: a
new error loop, a high-cardinality field, or a retry storm.

## Symptom

- CloudWatch / Datadog / Loki ingest bill jumps 5-10x in a single day.
- `otelcol_exporter_send_failed_log_records` or Loki `rate_limit` errors
  spike — your collector is dropping logs it cannot push fast enough.
- Searching logs for the incident takes minutes instead of seconds because
  the backend is overloaded.
- A Grafana panel showing log bytes-per-minute shows a clear step change
  starting at a specific deploy timestamp.
- The same log line appears thousands of times per second — a tight error
  loop or retry storm.

## Gotchas

- **Cardinality is the silent killer, not raw bytes.** A label/field with
  unbounded values (`user_id`, `request_id`, `email`, full URLs with query
  strings) explodes index size. Loki calls this "high cardinality labels";
  Datadog calls it "custom metric cardinality." 1M unique `request_id` values
  can cost more than 1GB of plain text logs.
- **Never put `request_id` or `trace_id` in a Loki label.** Labels are
  indexed; log lines are not. Put IDs in the log body and use LogQL
  `{job="api"} |= "trace_id=abc123"` to filter — slow but cheap.
- **Datadog custom metric cardinality is billed separately.** Submitting
  `user.email` as a tag creates one metric per unique email, billed as custom
  metrics. Use a log facet (indexed attribute) only when truly needed.
- **Exception logging is the most common spike cause.** A retry loop with no
  backoff logs the same stack trace every 100ms. Add a `retry_count` cap or
  exponential backoff with jitter, and never log the full stack on every
  retry — log once per N retries.
- **HTTP access logs at high RPS are surprisingly costly.** 10k req/s with a
  500-byte access log = 1.7 GB/day just for access lines. Sample them or
  route them to a cheaper tier (e.g. S3 via Loki chunk caching) instead of
  the live-query tier.
- **Debug-level logs accidentally enabled in prod.** A single
  `LOG_LEVEL=debug` flag flipped in a deploy can 50x your volume. Alert on
  log volume change correlated with deploy events.
- **Log forwarding fan-out doubles the bill.** If you ship to both Loki and
  Datadog "for redundancy" you pay twice. Pick one primary and one cheap
  archive (S3) for the other.

## Example: Detecting the spike (Prometheus + Loki)

```promql
# 5-minute log rate by job, alert if >10x the 1-hour baseline
sum by (job) (rate(loki_distributor_lines_received_total[5m]))
  >
10 * sum by (job) (rate(loki_distributor_lines_received_total[1h] offset 10m))
```

Alert: "Log volume for job=X is 10x baseline" → page the on-call to
investigate before the bill compounds.

## Example: Finding the high-cardinality culprit in Loki

```logql
# Top labels by series count — the label with the most unique values is the culprit
topk(10, count by (status, method, route) (count_over_time({job="api"}[5m])))
```

If a single label combination produces wildly more series than peers, that is
your cardinality leak. Common offenders: `route` containing the resource ID
(`/users/12345` instead of `/users/:id`), `instance` with ephemeral IPs, or
`status` containing the full error string.

## Example: Rate-limiting the noisy service

In the OpenTelemetry Collector, cap log throughput per service so one noisy
service cannot starve the rest:

```yaml
processors:
  filter/logs:
    logs:
      log_record_attribute:
        - key: http.route
          value: "/health"
          op: drop         # don't ingest health-check spam
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [memory_limiter, filter/logs]
      exporters: [loki]
```

For hard caps, put a rate-limiter proxy (e.g. Vector `sample` transform, or
Fluent Bit `throttle` filter) in front of the exporter.

## Verifying it works

- Set a budget alert at 1.5x your normal daily ingest. If it fires, you find
  out in minutes, not when the monthly bill arrives.
- Audit all indexed fields/tags quarterly. Remove anything whose unique-value
  count is unbounded or grows over time.
- After a deploy, watch the log-volume panel for 15 minutes. A step change =
  a deploy regression, not a usage increase.
