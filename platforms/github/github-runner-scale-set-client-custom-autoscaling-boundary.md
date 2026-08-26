# Runner Scale Set Client custom autoscaling boundary

**Issue:** GitHub identifies Actions Runner Controller as the recommended Kubernetes autoscaling solution. The Runner Scale Set Client is a complementary interface for custom autoscalers outside Kubernetes, not an ARC replacement.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use ephemeral one-job runners, immutable images, isolated runner groups, exact labels, and externally retained runner logs.
- Authenticate the control plane with a narrowly permissioned GitHub App; separate provisioning credentials from job credentials.
- Bound scale-out, queue age, idle capacity, registration failures, and teardown retries; quarantine a runner whose cleanup cannot be proved.

## Verification

1. Deliver queued, in-progress, completed, duplicate, delayed, and out-of-order lifecycle events.
2. Prove one job per runner and deregistration plus host destruction after cancellation.
3. Simulate control-plane outage and verify jobs do not fall back to a privileged persistent runner.

## Gotchas

Webhooks can be delayed or lost, so a webhook-only replica count is not authoritative. Autoscaling improves capacity, not the trustworthiness of code dispatched to the runner.

## Official sources

- https://docs.github.com/en/actions/reference/runners/self-hosted-runners
