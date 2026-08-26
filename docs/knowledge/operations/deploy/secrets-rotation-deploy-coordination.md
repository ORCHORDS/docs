# secrets-rotation-deploy-coordination

**Issue:** Rotating credentials in a running system without downtime is a sequencing problem, not a security problem: revoke too early and every instance still holding the old secret starts failing; write the new value before consumers reload it and you race your own deploy. Current guidance (AWS alternating-rotation strategy, Vault dynamic secrets, 2025-2026 writeups) converges on one core pattern — dual-valid credentials with an overlap window longer than any consumer's cache — and on treating rotation as a deploy-like change with verification gates. This article covers the general coordination pattern for application secrets; image-pull-secrets-rotation covers the Kubernetes registry-credential subset and gitops-secrets-management covers secret storage.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The overlap-window pattern

1. **Two credentials, both valid.** The only zero-downtime rotation primitive is a period where old and new credentials authenticate simultaneously (the dual/alternating secrets approach). Any rotation scheme without an overlap window has a built-in outage.
2. **Alternate storage slots.** Store credentials in versioned slots (AWS Secrets Manager alternating users, a secret named `db-cred-a`/`db-cred-b`, or a map with two keys) so writing the new value never clobbers the value consumers still read.
3. **Consumers must tolerate either.** Readers load whichever slot is current at boot or refresh; the system invariant is that during rotation, both slots authenticate.
4. **Revoke is a separate, later step.** Revocation is its own change with its own verification, never bundled into the rotation deploy; bundling is what turns a bad rotation into an outage.

## Rotation as a four-step deploy

1. **Create.** Issue the new credential alongside the old one; verify it works with a direct authentication test before anything depends on it.
2. **Propagate.** Deliver the new secret to consumers — restart, re-deploy, or refresh — using the normal deploy pipeline so rotation inherits its batching, health checks, and rollback.
3. **Verify.** Confirm every consumer actually authenticates with the new credential (connection metrics, logs, manager-side last-used timestamps) before scheduling revocation.
4. **Revoke.** Invalidate the old credential only after the overlap window has outlasted every cache, long-lived connection, and external client. Then delete the old slot's stored value.

## Sizing the overlap window

1. **Longer than the longest consumer cache.** The documented failure pattern (for example ECS tasks caching stale RDS credentials) is an overlap window shorter than the process's secret cache TTL. The window must exceed max cache TTL plus one full deploy cycle.
2. **Longer than long-lived connections.** Database pools and gRPC channels authenticate at establishment; if connections live for days, either the window is days or you must force reconnects inside it.
3. **Long enough for external clients.** Third parties holding your API keys follow their own reload schedule; contractual rotation notices plus a generous window are the only levers you have.
4. **Not so long it becomes never.** Cap the window (typically hours to days) and alarm on overdue revocations, or "temporary" dual-valid credentials become permanent attack surface.

## Failure modes

1. **A consumer missed the update.** Verification must count consumers, not assume them: any instance still on the old credential at revoke time is an outage. Track credential version per instance in metrics.
2. **Revoke raced a deploy.** Revoking while a rolling deploy is mid-flight lets new instances boot with a stale cached secret; block revocation during deploy windows.
3. **Rotation broke the rotator.** If the rotation job itself uses the credential it rotates, a partial failure can lock out the rotator; it needs its own bootstrap credential with separate privileges.
4. **Silent dual validity forever.** Alert on secrets with two valid versions older than the policy window; overlap is a state, not a lifestyle.

## Cadence and ownership

1. **Automate to reach short TTLs.** Automated alternating rotation supports intervals as short as hours (AWS supports rotation down to roughly every four hours); manual rotation supports quarters. Choose cadence by what your automation sustains, not by aspiration.
2. **Prefer dynamic secrets where possible.** Vault-style short-TTL credentials (1-24 hours) collapse the coordination problem: overlap logic lives in the agent and revocation is implicit in expiry.
3. **Rotate on events, not just schedule.** Offboarding, laptop loss, vendor compromise, and leak suspicion trigger out-of-band rotation; the runbook for that must already exist and be rehearsed.
4. **Tie rotations to deploy telemetry.** Each rotation is a change: annotate dashboards, record the four-step timeline, and feed anomalies into the same incident pipeline as deploys.
