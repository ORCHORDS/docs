# Workers Queues Backpressure and Concurrency Limits

Queues decouple producers from consumers, but the decoupling only works if the consumer side is tuned to the traffic reality: too little concurrency and the backlog grows until messages age out; too much and the consumer hammers a downstream database into failure. Cloudflare Queues gives the tuning knobs — consumer concurrency, batch size, waits, retries, and a dead-letter destination — and backpressure emerges from how they combine. This article is the checklist for setting those knobs deliberately and proving they hold under stress.

## Scope

Applies to Workers consuming from Cloudflare Queues where throughput, backlog growth, or downstream tolerance is a concern. Covers consumer concurrency configuration, batch settings, retry behavior, dead letter queue (DLQ) wiring, and the limit ceilings that bound them. Excludes producer-side rate shaping, Queues-over-HTTP ingestion patterns without a Worker consumer, and cross-account fan-out designs.

## Workflow or implementation guidance

1. Measure the inbound rate first. Peak messages per second and message size distribution define what the consumer must sustain; without them, concurrency tuning is guesswork.
2. Determine downstream tolerance: maximum sustainable writes per second against the database or API the consumer calls, including any connection pool ceiling that interacts with concurrent consumer invocations.
3. Set the maximum batch settings (`max_batch_size`, `max_batch_timeout`, `max_concurrency`, `max_retries`) as explicit values in the queue consumer configuration rather than relying on defaults, so capacity is a decision rather than an accident.
4. Start concurrency conservatively at or below the downstream ceiling divided by per-message downstream cost, then load test at projected peak and watch two signals: queue consumer lag (backlog depth and oldest-message age) and downstream error rate.
5. Configure the retry policy consciously: `max_retries` per message, and understand that each retry re-delivers the message; retries multiply load exactly when the system is struggling.
6. Wire a dead letter queue before the first production traffic. A consumer that exhausts retries without a DLQ silently drops messages under the default behavior.
7. Make consumer handlers idempotent, because retries and at-least-once delivery mean the same message can be processed more than once; partial batch failure re-delivers other messages from the batch.
8. Establish steady-state monitoring on backlog depth and message age, and define an alert threshold that fires well before the maximum message retention period (14 days) becomes a data-loss risk.

## Controls

- Explicit-capacity control: `max_concurrency`, `max_batch_size`, and `max_retries` are pinned in configuration and reviewed against measured rates quarterly or on major traffic change.
- Downstream ceiling budget: documented maximum downstream operations per second attributable to the consumer, with concurrency set so worst-case burst stays inside it.
- DLQ-required policy: no consumer reaches production without a dead letter queue attached and a triage procedure for DLQ contents.
- Idempotency test gate: the consumer's test suite includes a duplicate-delivery case proving double processing is harmless.
- Backlog alert thresholds: warning before the backlog threatens the retention window; critical when age trends toward it.
- Concurrency change approval: raising concurrency is treated like a capacity change for the downstream, with the same review, because that is its effect.

## Validation evidence

- Load test report showing sustained and peak message rates against configured concurrency, with backlog depth staying flat or draining.
- Configuration excerpt with the explicit `max_concurrency`, `max_batch_size`, `max_batch_timeout`, and `max_retries` values as deployed.
- Downstream saturation evidence: database or API metrics during the load test demonstrating the consumer stays within the documented ceiling.
- Retry behavior demonstration: a fault-injection run where messages fail and are retried the configured number of times, then land in the DLQ.
- Idempotency test output: the same message delivered twice with the duplicate case neutralized.
- Alert verification: a synthetic backlog that trips the warning threshold and pages the on-call rotation.

## Failure modes and correction

- Backlog grows unbounded during peaks: raise `max_concurrency` only after confirming downstream headroom; otherwise add consumer-side efficiency (batch downstream writes) before adding parallelism.
- Consumer trips downstream rate limits at moderate concurrency: lower concurrency, add jitter or client-side backoff to downstream calls, or batch downstream operations so each invocation costs fewer requests.
- Poison message loops: a message that deterministically fails exhausts retries and lands in the DLQ — correct outcome — but a batch-dominant failure pattern that re-delivers good messages repeatedly indicates the handler should checkpoint per-message progress before failing.
- Retries amplify an incident: retries of a transient downstream outage stack on recovery; prefer fewer retries with DLQ triage over many retries when the downstream is fragile.
- DLQ fills silently with no owner: DLQ depth is monitored like a production queue, with a triage runbook naming who looks and how often.
- Concurrency raised to mask a slow handler: the underlying per-message latency problem resurfaces at the next peak; profile and fix the handler instead.

## Limitations

- Consumers scale automatically up to the configured maximum concurrency; they cannot be pinned to exactly one invocation without setting that maximum.
- Message retention is bounded (up to 14 days); a stalled consumer eventually loses messages, which is why backlog age alerts matter.
- At-least-once delivery is a contract: exactly-once processing is not achievable, only idempotent handlers.
- Backpressure from Queues to producers is indirect — producers see admission and throughput behavior, not an explicit slow-consumer signal.
- Very large batches can increase per-invocation CPU pressure; batch size tuning trades invocation count against per-invocation work.

## Canonical sources

- Cloudflare Queues docs, "Consumer concurrency": https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- Cloudflare Queues docs, "Limits": https://developers.cloudflare.com/queues/platform/limits/
- Cloudflare Queues docs, overview (batching, retries, dead letter queues): https://developers.cloudflare.com/queues/
