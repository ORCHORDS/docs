# cron-job-monitoring

**Issue:** Monitoring scheduled jobs to ensure they run on schedule and complete successfully
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A cron job silently fails or is delayed. No notification until downstream effects are noticed hours later.

## Pattern / Solution
Implement dead man's switch pattern: send a heartbeat ping to a monitoring service (OpsGenie heartbeat, Healthchecks.io, Cronitor) on successful completion. If ping is not received within expected window plus grace period, alert fires. Track job start time, end time, duration, and exit code. For Kubernetes CronJobs: monitor kube_job_failed and kube_job_complete via kube-state-metrics.

## Gotchas
Cron timezone bugs are common — always use UTC. Job overlaps cause resource contention — implement locking or skip-if-running. Log job output even on success. Kubernetes CronJob concurrency policy: use Forbid to prevent overlap, Replace to kill stale runs.

## Related
batch-job-monitoring, opsgenie-setup, queue-depth-monitoring, deployment-event-tracking
