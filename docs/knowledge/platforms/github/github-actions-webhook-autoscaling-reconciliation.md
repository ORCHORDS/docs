# Runner autoscaling webhook reconciliation

**Issue**

The `workflow_job` webhook supplies queued and completed signals for autoscaling, but delivery can be duplicated, delayed, reordered, or missed; raw event counting creates leaks or under-capacity.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Verify webhook signatures and store delivery IDs for idempotency.
- Key desired capacity by job identity and reconcile against GitHub state rather than increment/decrement counters alone.
- Apply label and runner-group eligibility before provisioning.
- Bound scale-out, provisioning time, idle expiry, and failure retries while preserving required job routing.

## Verification

1. Replay duplicates and completed-before-queued delivery.
2. Drop events and prove periodic reconciliation converges.
3. Test burst queues, provisioning failure, cancellation, and label mismatch.

## Gotchas

- A queued event does not mean every new runner can accept the job.
- Webhook acknowledgement is not provisioning success.
- Never mark required checks successful because capacity is unavailable.

## Official sources

- [GitHub autoscaling self-hosted runners](https://docs.github.com/en/actions/reference/runners/self-hosted-runners#autoscaling)
- [GitHub webhook events workflow_job](https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_job)
