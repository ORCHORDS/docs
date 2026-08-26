# batch-job-monitoring

**Issue:** Monitoring long-running batch jobs for progress, errors, and completion
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Batch job runs for hours with no visibility into progress or intermediate failures.

## Pattern / Solution
Emit progress metrics at regular intervals: records processed, records failed, records remaining, estimated completion time. Push metrics to Prometheus Pushgateway for short-lived jobs. Alert on stall detection: if progress rate drops to zero for more than 5min while job is running. Log structured records at job start, completion, and per-error. Track job run history for anomaly detection.

## Gotchas
Prometheus Pushgateway retains last-pushed metrics indefinitely — delete metrics after job completion. Long-running jobs that hold DB transactions block other operations — use smaller transactions and checkpointing. Monitor memory growth in batch jobs. Implement idempotent job logic so failed runs can be safely retried.

## Related
cron-job-monitoring, queue-depth-monitoring, slow-query-logging
