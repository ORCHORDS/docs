# postgres-listen-notify

**Issue:** Postgres ships a built-in publish/subscribe channel: `LISTEN channel` on one session, `NOTIFY channel, 'payload'` from any other, and listeners receive events in near-real-time. It is tempting to use it as a free message broker — cache invalidation, "row changed, refresh your view" pushes, waking background workers. It works, and for small deployments it is delightful. But LISTEN/NOTIFY has hard structural limits (RAM-only queue, 8000-byte payload cap, at-most-once delivery, same-database only, one dedicated connection per listener), and the 2025 recall.ai post "Postgres LISTEN/NOTIFY does not scale" documented how a moderate notification rate degraded an entire managed Postgres cluster, including replicas that never issued a LISTEN. Using it well means knowing exactly where its envelope ends.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Mechanics that determine everything else

1. **Delivery is at-most-once and fire-and-forget.** Notifications exist only in a per-listener RAM queue; if no session is listening, or the listener disconnects before processing, the notification is gone forever. Any use of LISTEN/NOTIFY must tolerate lost messages by design — it is a wake-up hint, never a data transport.
2. **Payloads are capped at 8000 bytes.** `NOTIFY` fails outright with larger payloads; the standard pattern is to send only an id (`NOTIFY row_changed, '42'`) and have the listener fetch the row, which also avoids the staleness of embedded snapshots.
3. **One dedicated long-lived connection per listener.** `LISTEN` is a session-level property, so each listener process must hold a connection that does nothing else. That connection comes out of your connection budget, cannot go through transaction-mode pooling (PgBouncer doesn't forward notifications), and on managed platforms (RDS, Cloud SQL) it is exposed to idle-timeout kills that silently stop your events until reconnect logic notices.
4. **Notifications fire after commit, and duplicates are coalesced.** If one transaction sends the same channel/payload twice, listeners receive it once — convenient deduplication, but also a trap if you expected two events for two logical changes; make payloads unique (include the row id and a version).

## Why it stops scaling (the 2025 evidence)

1. **Every NOTIFY taxes every replica.** As recall.ai documented, the notification queue is replicated through WAL, and each standby's walreceiver wakes for every notification even if nobody on that node is listening — a cluster-wide cost that grows linearly with total notification volume and is completely invisible to per-database metrics.
2. **The queue is unbounded RAM.** The per-listener queue lives in memory on the primary; a listener that processes slower than producers publish grows memory until OOM or intervention. There is no persistence, no ack, no replay, and no backpressure mechanism.
3. **One chatty feature degrades everyone.** Because channels are global to the database, a debug feature notifying per-row during a bulk import can degrade an otherwise quiet cluster; there is no per-channel rate limiting or quota.
4. **Failover drops listeners.** On promotion, standbys don't carry LISTEN registrations (they couldn't have — they were read-only); after a failover every listener must reconnect to the new primary. Clients that don't implement reconnect-with-backoff plus a catch-up query go deaf permanently.

## Legitimate uses that hold up well

1. **Cache invalidation with a fallback TTL.** The classic sweet spot: LISTEN/NOTIFY hints "evict key X now", while a maximum TTL on cached entries bounds the damage of any lost notification. Correctness comes from the TTL; the notify is purely a latency optimization.
2. **Waking pollers to cut latency.** A worker that polls a jobs table every 30 seconds can subscribe to a `job_enqueued` channel and poll immediately on notify — the polling loop remains the source of truth, so a lost notify costs latency, not correctness.
3. **Local dev and single-node deployments.** For modest volumes (hundreds of notifications per minute) on one primary with few replicas, LISTEN/NOTIFY is a zero-infrastructure win; just instrument notification volume so you notice before the envelope is exceeded.
4. **Sending ids, not objects.** Keep payloads tiny and id-like in all cases; it sidesteps the byte cap, keeps the RAM queue shallow, and forces listeners to read current state rather than trusting an embedded snapshot.

## What to move to when you outgrow it

1. **Outbox table + poller or CDC.** Write events to an outbox table in the same transaction as the data change (atomicity LISTEN/NOTIFY cannot offer), then deliver via polling workers or Debezium CDC to Kafka; consumers get persistence, replay, and backpressure.
2. **A real message broker.** When fan-out to many services, durable subscriptions, or dead-lettering matter, RabbitMQ/NATS/Kafka are the honest answer; Postgres signals between processes that share the database, not a general event backbone.
3. **Polling with a notify fast-path (hybrid).** Keep a periodic query as the correctness mechanism and NOTIFY as the accelerator — this is the pattern that survives lost notifications, pooler restrictions (poll via pooled connections), and failovers, at the cost of baseline latency equal to the poll interval.
4. **Logical replication for cross-database delivery.** If the real requirement is "another database reacts to changes", logical decoding delivers ordered, durable change streams that LISTEN/NOTIFY was never designed to provide.
