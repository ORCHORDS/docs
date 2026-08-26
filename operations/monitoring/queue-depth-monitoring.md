# queue-depth-monitoring

**Issue:** Monitoring message queue depth as a leading indicator of processing backlog and consumer health
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers are running but messages accumulate. Queue depth is the earliest signal of processing degradation.

## Pattern / Solution
Export queue depth metrics for RabbitMQ, SQS, Kafka, BullMQ. For SQS use CloudWatch ApproximateNumberOfMessagesVisible. For Kafka monitor consumer group lag. Alert when depth exceeds N messages or when depth grows faster than consumer throughput. Track dead-letter queue depth separately — DLQ growth indicates persistent processing failures.

## Gotchas
Queue depth alone is misleading — also track message age. SQS visibility timeout affects the visible count. Kafka lag is per partition — monitor max lag, not sum. Autoscaling consumers based on queue depth requires careful scale-down hysteresis.

## Related
worker-cpu-monitoring, batch-job-monitoring, connection-pool-monitoring, cron-job-monitoring
