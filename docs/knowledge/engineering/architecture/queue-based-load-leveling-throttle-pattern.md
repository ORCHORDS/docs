# Queue Based Load Leveling Throttle Pattern

## Scope

This article addresses the queue-based load leveling pattern (also called the queue-based throttling pattern) as catalogued in the Microsoft Azure Architecture Center. It explains how a queue between a producer and a consumer decouples their rates, smooths bursty traffic, and protects the consumer from saturation. The discussion covers the role of the queue as a buffer, the choice of queue technology, the producer-side and consumer-side concerns, the backpressure and dead-letter handling, and the relationship to the competing consumers and priority queue patterns. The article applies to any system that has a producer-consumer relationship with rate asymmetry: HTTP front ends backing work onto asynchronous workers, IoT devices reporting telemetry, batch jobs submitting tasks to compute pools.

## Workflow or implementation guidance

Queue-based load leveling inserts a queue between a producer and a consumer. The producer writes work to the queue at its own rate and returns immediately. The consumer reads work from the queue at its own rate and processes it. The queue is the buffer that absorbs the difference between the producer's peak rate and the consumer's sustained rate. When the producer is fast and the consumer is slow, the queue grows; when the producer is slow and the consumer is fast, the queue empties.

The first step in implementation is to identify the rate asymmetry. If the producer and the consumer have the same rate and the same burst tolerance, a queue is unnecessary overhead. If the producer has bursty traffic and the consumer has steady throughput, a queue is essential. The second step is to choose the queue technology. Cloudflare Queues, AWS SQS, Azure Service Bus, RabbitMQ, and Kafka each have different guarantees around ordering, delivery, retention, and throughput. The choice depends on the application's requirements: at-least-once delivery, ordered delivery within a partition, message TTL, dead-letter handling.

The third step is to size the queue. The queue must be large enough to absorb a representative burst (a minute of peak traffic, an hour of peak traffic, depending on the consumer's recovery time), but bounded enough to prevent unbounded growth. A queue that grows without bound is a sign that the consumer is falling behind and that backpressure is not being applied. The fourth step is to design the producer side. The producer must handle queue-write failures (retry with backoff, return an error to the caller, or persist the work locally and retry asynchronously). The producer must also be observable: the queue-write rate, the queue-write latency, and the queue-write failure rate must be tracked.

The fifth step is to design the consumer side. The consumer must scale out to match the queue's depth: more consumers when the queue is deep, fewer when the queue is shallow. The consumer must handle poison messages (messages that consistently fail) by routing them to a dead-letter queue rather than blocking the main queue. The consumer must be idempotent because at-least-once delivery means a message may arrive more than once.

The sixth step is to plan for backpressure. If the queue is full and the consumer cannot keep up, the producer must be told to slow down. The mechanism for this depends on the queue technology: a bounded queue that rejects new writes, a return code that the producer interprets as "back off", or a circuit breaker at the producer that opens when the queue depth crosses a threshold.

## Controls

Queue-based load leveling controls cover queue depth, message TTL, dead-letter handling, and observability. Queue depth must be monitored and alerted: a queue that grows unboundedly is a symptom of consumer saturation or producer over-load. Message TTL must be set: messages that have been in the queue longer than the application's tolerance must be expired and either dropped or routed to a dead-letter queue. Dead-letter handling must be documented: messages in the dead-letter queue must be inspected, reprocessed, or purged.

Producer-side controls include idempotency keys on messages, structured payloads, and retry-with-backoff on queue-write failures. Consumer-side controls include idempotent processing, exponential backoff on transient failures, and explicit handling for poison messages.

Observability must include end-to-end latency (the time from "producer wrote the message" to "consumer processed the message"), which is the latency that the application's user actually experiences. Without this metric, the queue is invisible to the user.

## Validation evidence

Validation must prove that the queue absorbs bursts. A burst test drives the producer at 10x its normal rate for a short period and verifies that the queue grows, the consumer processes the backlog, and no messages are lost. The test must cover the failure path: a consumer crash mid-processing must not lose messages (because the message is not acknowledged until processing completes) and must not double-process messages (because the consumer is idempotent).

Validation must also prove that backpressure works. A test deliberately saturates the consumer and observes that the queue depth grows, the producer's write rate slows (or its writes are rejected), and the system does not collapse under the load. The test must also prove that the system recovers: when the consumer is restored, the queue drains, and the producer returns to its normal rate.

## Failure modes and correction

The dominant failure is the queue becoming a black hole. Messages are written to the queue and never processed. The consumer has crashed silently, or the dead-letter queue is never inspected. The cure is monitoring and alerting on queue depth and on consumer health. A second failure is the queue being unbounded. The queue grows to consume all available disk or memory and the queue itself crashes. The cure is a bounded queue with explicit backpressure and a documented retention policy.

A third failure is message loss during a queue crash. A queue that is not durable loses messages when it crashes. The cure is to choose a durable queue (SQS with persistent storage, RabbitMQ with persistent messages, Kafka with replication) and to validate the durability with a crash test. A fourth failure is the consumer not being idempotent. A duplicate message causes a duplicate side effect (a duplicate email, a duplicate charge). The cure is to design the consumer to be idempotent against the message ID.

A fifth failure is the queue hiding a deeper problem. The consumer is slow because it is talking to a downstream that is slow; the queue absorbs the slowness, and the user does not see the symptom, but the system is degrading. The cure is to monitor end-to-end latency and to alert when the queue alone cannot hide the downstream's slowness.

## Limitations

Queue-based load leveling does not reduce the total work; it only delays it. A consumer that is permanently too slow will eventually back up the queue no matter how large the queue is. The queue adds latency: every message pays the cost of being enqueued and dequeued. For latency-sensitive workloads, the queue may be unacceptable. The queue also adds operational surface area: another service to monitor, another failure mode to handle, another cost to budget.

The pattern is also not a substitute for capacity planning. If the consumer's sustained throughput is lower than the producer's sustained rate, the queue will grow until the consumer catches up or until the queue is exhausted. The pattern works for bursts; it does not work for sustained imbalance.

## Canonical sources

- Microsoft Azure Architecture Center — *Queue-Based Load Leveling pattern*: https://learn.microsoft.com/en-us/azure/architecture/patterns/queue-based-load-leveling
- Microsoft Azure Architecture Center — *Competing Consumers pattern*, the companion pattern for scaling the consumer side: https://learn.microsoft.com/en-us/azure/architecture/microservices/
- AWS Architecture Blog — *Queue-based architectures* and the related posts on backpressure and dead-letter handling
- Chris Richardson — *Microservices Patterns* (Manning), the async messaging chapters and the queue-based load leveling catalog entry
