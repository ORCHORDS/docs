# Deployment live-revision verification and rollback evidence

**Issue:** CI reports a successful deployment, but operators cannot prove which immutable revision is serving production or safely determine whether a rollback has actually taken effect.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Decision

Treat “deployment succeeded” and “the intended revision is live” as separate assertions. Every production release must expose a non-sensitive immutable revision identifier, correlate it with the approved build/deployment record, and verify it from the live endpoint before marking the release complete.

## Pattern

1. Build an immutable artifact and record its source revision, artifact digest, environment, and deployment ID.
2. Deploy only that approved artifact.
3. Attach the revision/deployment identifier to deployment telemetry and, where appropriate, a protected health/version endpoint or response header.
4. Run post-deploy smoke checks against the actual production route.
5. Compare the observed live revision with the approved target. Fail the release and begin rollback investigation on mismatch.
6. During rollback, repeat the same observation—do not infer success from a control-plane acknowledgement alone.

## Verification

- the live endpoint identifies the expected revision without exposing internal topology, secrets, or customer data;
- deployed revision, artifact digest, source commit, and change approval are traceable in one record;
- a deliberately failed/partial rollout is detected as a mismatch;
- cached assets and edge regions are tested so an old revision cannot be mistaken for the new default;
- rollback exercises confirm both control plane and live traffic return to the intended prior revision.

## Gotchas

- Do not use a mutable branch name as revision evidence.
- “Healthy” only proves the process can respond; it does not prove it is the approved build.
- If public revision disclosure is unacceptable, use authenticated synthetic checks and private telemetry instead.
- Keep feature-flag state separate from artifact version: both can alter live behavior.

## Related

- `deploy/rollback-strategy.md`
- `deploy/canary-deployments.md`
- `cloudflare/workers-version-metadata-deployment-correlation.md`
- `monitoring/deployment-observability.md`
