# OpenTelemetry Collector Pipeline Reliability

A Collector sits between SDKs and storage, which makes it simultaneously a buffer, a transformer, and a single point of failure. When a backend slows or an upstream surges, the collector's internal queueing, retry, and memory limiting decide whether telemetry is delayed, dropped, or the process is OOM-killed. This article covers how to compose those mechanisms into a pipeline that degrades predictably: bounded memory via the memory limiter, absorbing short outages via retry and sending queues, and surviving restarts via persistent queues.

## Scope

Covers the exporter-facing reliability mechanisms of the OpenTelemetry Collector: the memory limiter processor, per-exporter retry and queue configuration (the exporterhelper settings available on most exporters), and the file storage extension used for persistent queues. Also covers processor ordering, sizing guidance, and how to observe the pipeline's own health. Excludes tail sampling policy design, component-specific transformation logic, and the gateway-versus-agent topology decision except where it affects queue sizing.

## Workflow or implementation guidance

Order processors deliberately, then size buffering in three tiers.

Processor ordering comes first because the memory limiter is only effective early in the pipeline. The canonical order is: memory limiter (first, so it sees everything entering), then resource and attribute processing, then batching last, immediately before export. Batching after the memory limiter means rejected batches never consume exporter memory; putting the memory limiter last would let the pipeline spend memory transforming data it is about to refuse.

Tier one — memory limiter. Configure `check_interval`, `limit_mib`, and `spike_limit_mib`. The limiter refuses data (returning retryable errors to receivers) once usage crosses the soft limit and refuses everything above the hard limit until usage falls back below the soft threshold. Size the limit at roughly half to two-thirds of the container's memory request so headroom exists for batch assembly and in-flight exports. On an agent colocated with the application, the limiter also protects the host process from a telemetry-driven OOM that would take the workload down with it.

Tier two — retry and in-memory queue. Every exporter built on exporterhelper accepts a `retry_on_failure` block (queue classification of retryable errors, exponential backoff with `initial_interval`, `max_interval`, and `max_elapsed_time`) and a `sending_queue` block (`enabled`, `num_consumers`, `queue_size`). Retry absorbs transient backend errors; the queue decouples the pipeline from exporter latency. Set `max_elapsed_time` to match the backend's worst realistic outage window you are willing to hold in memory — five minutes is a common starting point — and bound `queue_size` so a prolonged outage produces predictable drops at the queue head rather than unbounded growth. When the queue is full the oldest or newest data is refused depending on the queue implementation, so the drops are visible in the exporter's refused-Items counter rather than hidden.

Tier three — persistent queue. Extend the sending queue with `storage: file` (or the storage extension identifier configured in your distribution) so queued telemetry survives collector restarts. The file storage extension writes to a local directory that must be on a volume that outlives the pod and be excluded from concurrent writes by replicas. Persistent queues trade disk I/O and some throughput for restart survival; enable them on gateway collectors where losing in-flight telemetry during a rolling restart is unacceptable, and usually leave agents on in-memory queues where the cost of losing a few seconds is acceptable.

Finally, expose the collector's own telemetry: enable internal metrics and the health check extension, and alert on queue persistence failures, retry exhaustion, and refused items per receiver. A reliable pipeline is one whose drops are counted and alarmed, not one that never drops.

## Controls

- Memory limiter configuration with explicit soft and hard thresholds derived from the container memory request, plus an alert on the limiter's refusal counter.
- Processor order enforced by a configuration lint (memory limiter first, batch last) in CI.
- `sending_queue.queue_size` and `retry_on_failure.max_elapsed_time` set per exporter with a documented rationale tying each number to a backend outage budget.
- File storage extension volume with a dedicated mount, sized to hold queue_size batches at the observed average batch size, and monitored for write errors.
- Health check extension wired into load balancer readiness so a wedged collector stops receiving traffic.
- Weekly chaos drill: block the backend endpoint for the retry budget duration and assert the pipeline drains without drops once unblocked.

## Validation evidence

Demonstrate reliability with a controlled outage test: point a staging collector at a blackholed backend, drive a fixed-rate synthetic load, verify the queue grows to its bound and refused items climb (proving bounded behavior), then restore the backend and confirm queued data drains and the refused-item rate returns to zero. Capture the collector's own metrics during the drill — `exporter_queue_size`, retry counters, memory limiter refusals — as the evidence artifact. A second artifact is a restart test: kill the collector with a full persistent queue, restart it, and verify the post-restart export count plus the pre-kill count equals the produced count within a declared tolerance.

## Failure modes and correction

- OOM kills despite the memory limiter: the limit was set too close to the container request, or a processor after the limiter allocates heavily (for example, a transform holding large batches). Lower `limit_mib`, move the limiter's check interval down, and profile the offending processor.
- Persistent queue corrupted after an unclean shutdown: verify a single writer per directory; replicas sharing a storage volume corrupt the WAL. Give each collector its own volume or disable the persistent queue on replicas.
- Retry storm hammering a recovering backend: `max_elapsed_time` and backoff multipliers too aggressive. Increase `initial_interval`, cap `max_interval`, and ensure the backend's throttle responses (429 with Retry-After) are honored rather than retried immediately.
- Silent data loss with no counter movement: a receiver accepted data but the exporter's queue refused it before accounting, or a connector dropped it. Enable per-component telemetry and route receiver-level metrics into the same alerting as exporter metrics.
- Queue drains but backend reports gaps: the drain raced ahead of the backend's ingestion ordering. Check for out-of-order timestamps and use a backend that accepts them within its configured window.

## Limitations

Queue and retry blocks are implemented by exporterhelper, so third-party exporters built outside that framework may expose different or no options; verify per component. Persistent queues protect only what has reached the queue — data still in receiver buffers or unacknowledged from SDKs is lost on crash. The memory limiter reacts to the collector's own heap, not system-wide pressure, so it cannot defend against unrelated processes on a shared node. Sizing guidance here is empirical starting points, not guarantees; real numbers depend on payload shapes and must be derived from observed batch sizes.

## Canonical sources

- OpenTelemetry Collector configuration (processors, exporters, extensions): https://opentelemetry.io/docs/collector/configuration/
- OpenTelemetry Collector scaling guidance: https://opentelemetry.io/docs/collector/scaling/
- Collector benchmarks for sizing comparisons: https://opentelemetry.io/docs/collector/benchmarks/
