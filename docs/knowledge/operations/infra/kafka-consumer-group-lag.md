# kafka-consumer-group-lag

**Issue:** Monitoring and reducing Kafka consumer group lag before it causes processing backlogs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A Kafka consumer group falls behind producers. Messages accumulate in the topic partition. Downstream services see delayed data, retries pile up, or the consumer eventually times out and triggers rebalances that worsen lag.

## Pattern / Solution
Measure lag continuously, alert early, and scale consumers or optimize processing before the backlog grows unmanageable.

**Check lag from the CLI:**
```bash
# Total lag per group
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --group my-group --describe

# Output columns: GROUP, TOPIC, PARTITION, CURRENT-OFFSET, LOG-END-OFFSET, LAG
```

**Prometheus metrics (kafka_exporter or Strimzi):**
```yaml
# Alert: lag growing for > 5 minutes
- alert: KafkaConsumerLagHigh
  expr: kafka_consumer_group_lag > 10000
  for: 5m
  labels:
    severity: warning

- alert: KafkaConsumerLagCritical
  expr: kafka_consumer_group_lag > 100000
  for: 2m
  labels:
    severity: critical
```

**Common causes and fixes:**

| Cause | Fix |
|-------|-----|
| Too few consumer instances | Scale consumer group up (max = partition count) |
| Slow message processing | Profile; parallelize within consumer; push work to thread pool |
| Consumer rebalancing loop | Fix `max.poll.interval.ms` vs processing time mismatch |
| Small `max.poll.records` | Increase (default 500); tune batch size |
| Network or broker saturation | Add brokers; increase `fetch.max.bytes` |

**Tune consumer config (Java/Kafka client):**
```properties
max.poll.records=1000
max.poll.interval.ms=300000   # must exceed longest processing batch
session.timeout.ms=45000
fetch.max.bytes=52428800      # 50 MB
```

**Reset consumer offset (last resort, causes reprocessing):**
```bash
# Stop all consumers in the group first
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --group my-group --topic my-topic \
  --reset-offsets --to-latest --execute
```

## Gotchas
- Consumer count cannot exceed partition count — extra instances sit idle. Increase partition count before scaling consumers (partition count is irreversible to decrease).
- `max.poll.interval.ms` timeout triggers a rebalance that pauses all consumers in the group for 10–30 seconds, compounding lag.
- Lag of 0 does not mean real-time processing — the consumer may be at the end of a low-throughput topic that was never written to.
- Committing offsets too early (before processing is complete) causes message loss on consumer restart; commit after acknowledgment.

## Related
- `rabbitmq-dead-letter-queues.md`
- `elasticsearch-index-management.md`
- `prometheus-alertmanager-config.md`
