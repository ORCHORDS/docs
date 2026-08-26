# Kubernetes CronJob missed-schedule contract

**Issue:** A CronJob schedule is approximate, so controller downtime, clock skew, suspension, and overlapping runs can create duplicate work or permanently skip an occurrence.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Design the Job as idempotent and give each logical occurrence a deduplication key. Set `concurrencyPolicy` from workload semantics: `Allow` permits overlap, `Forbid` skips a due run while the previous one is active, and `Replace` stops the old run for the new one. Set `startingDeadlineSeconds` from business usefulness, not as a generic large number, and account for the controller's scheduling interval when choosing small values.

Declare `.spec.timeZone` where local civil time is required, monitor controller clock and missed-schedule events, and plan suspension/unsuspension: without an appropriate deadline, missed occurrences may be scheduled immediately when a CronJob resumes. Retain Job history separately from durable completion evidence.

## Verification

Test controller downtime below and above the deadline, a long-running prior Job under each concurrency policy, suspend/resume, daylight-saving transitions, duplicate creation, and more than the supported missed-schedule scan budget. Verify deduplication and alerts, not only Job creation.

## Gotchas

- CronJob does not provide exactly-once execution.
- `Forbid` overlap is counted as a missed schedule.
- Time-zone database changes can alter future civil-time runs.

## Official source

- [Kubernetes CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
