# dead-letter-queue-architecture

**Issue:** In an at-least-once event system, some messages can never be processed successfully — malformed payloads, events referencing deleted entities, consumer bugs, or dependencies that reject the data. Without a designed destination for these messages, teams get poison-pill loops (the same message retried forever, blocking the partition or queue), silent drops, or consumers crashing in a tight cycle. A dead-letter queue (DLQ) is the quarantine buffer that decouples the main flow from unprocessable work, but the architecture must go beyond merely parking messages: without failure classification, monitoring, and a deliberate redrive process, DLQs become landfills where data quietly disappears — the "where messages go to die" failure that 2025-era guidance repeatedly warns against.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Design Decisions

1. **Broker-native vs application-level DLQ.** SQS moves messages automatically via a redrive policy (maxReceiveCount then ARN of the DLQ); Kafka has no built-in DLQ topic mechanism, so the consumer itself must publish to a designated dead-letter topic on terminal failure. RabbitMQ can DLX via arguments. Decide explicitly which layer owns the decision: broker-level catches consumer crashes and timeouts, application-level can classify business vs technical failure — many systems need both.
2. **Retry-before-DLQ with backoff and jitter.** Distinguish transient from terminal failures before quarantining: retry transient errors with exponential backoff plus jitter (directly or via delayed redelivery), then move to the DLQ after a bounded attempt count. Retrying a schema-invalid message even once is wasted cycles; retrying a timeout-bursted message 20 times in a second is self-inflicted load.
3. **One DLQ per source queue/topic, not a global one.** A shared DLQ across heterogeneous consumers mixes schemas, ownership, and retry semantics, making replay dangerous — a redrive tool that republishes the mixed bag poisons every consumer at once. Scope DLQs to a single consumer group or queue, with matching retention.
4. **Enrich the message with failure metadata.** Wrap or attach headers on dead-lettering: original topic/queue, timestamp, attempt count, consumer version, exception type, stack or reason, and original key/partition. SQS flow-control messages carry arrival counts; Kafka consumers should emit structured failure records — without this context, triage means re-guessing history.
5. **Retention and durability.** DLQ data is often business-critical (an uncharged order, an unsent compliance notice). Set DLQ retention longer than the source (SQS default 4 days is a trap; set 14 days max), and define what happens at retention expiry — archive to object storage before drop, never silent expiry.

## Operating a DLQ

1. **Alert on depth and age, not just existence.** Alarm on DLQ message count greater than zero for N minutes and on oldest-message age; a graph nobody watches is where the landfill starts. Route DLQ alarms to the owning team of the source consumer, since they own the fix.
2. **Triage before any redrive.** The consistent practitioner guidance (AWS community, 2025 write-ups) is: never automatically redrive. First classify — payload bug, consumer bug, dependency outage, or genuinely unprocessable — because redriving unprocessed poison pills re-creates the original incident at machine speed.
3. **Fix-then-replay workflow.** The safe loop: classify the failure, ship the consumer or producer fix, deploy, replay a sample of one message, verify, then replay the batch (SQS console redrive, Kafka mirrormaker or a small replayer). Idempotent consumers are a hard prerequisite — replayed messages may duplicate ones that actually succeeded before the failure.
4. **Track DLQ metrics as SLOs.** Dead-letter rate (messages DLQ'd per million processed) per consumer is one of the best signal-quality indicators for event pipelines: a spike names the deploy that caused it, a slow rise names schema drift.
5. **Parking-lot pattern for business-rejects.** Messages that are valid but rejected by business rules (insufficient funds, duplicate entity) are not "dead" — route them to a business-exception queue with product-facing tooling, keeping the DLQ reserved for technical failure. This separation is what keeps DLQ volume meaningful as an error signal.

## Common Failure Modes

1. **Redrive loops between two queues.** A consumer of queue A dead-letters to B; a well-meaning automation replays B to A; the same failure re-dead-letters. Bound total redrive attempts with a hop counter header, and require human approval for replays above a size threshold.
2. **FIFO ordering violation on replay.** For partitioned or FIFO streams, dead-lettering and later re-inserting a message reorders it relative to successors that were processed. Design consumers to tolerate reorder on replay, or replay whole bounded sequences.
3. **Schema-drift poisoning after producer deploys.** A producer ships a breaking change; every message fails validation; the DLQ fills in minutes. Alarm thresholds must fire fast on rate-of-fill, and consumer contract tests (see contract-first design) should catch this in CI instead of production.
4. **DLQ as a garbage can for avoidable errors.** Timeouts, cold dependencies, and retryable 503s belong to the retry policy, not the DLQ; if your DLQ contents are 90 percent transient noise, the signal is diluted and real terminal failures get ignored.
5. **Cross-account and compliance blind spots.** DLQs in another account or region often miss alarms and access reviews, while containing exactly the regulated payloads (payments, PII) that retention and encryption policy must cover. Include DLQs in security review scope, with SSE and least-privilege access like any production data store.

## Related Patterns

1. **Retry and backoff patterns.** The retry ladder in front of the DLQ — see retry-pattern and timeout-pattern for tuning the transient-failure path.
2. **Outbox and inbox patterns.** Guaranteed publish plus idempotent consume shrinks the DLQ-eligible failure surface to genuine terminal cases.
3. **Circuit breakers.** When failures come from a dependency outage rather than message content, a breaker pauses consumption instead of dead-lettering thousands of messages that would succeed after recovery.
