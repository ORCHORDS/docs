# always-test-rollback-before-deploying

**Issue:** Rollback procedures that have never been tested fail exactly when they are needed most
**Date:** 2026-08-11
**Status:** documented

## What happened
A payment-processing service shipped a breaking schema migration on a Friday afternoon. The deploy went fine but a silent data-type mismatch caused incorrect fee calculations. The team attempted to roll back but discovered the rollback migration had never been written and the previous Docker image was missing from the registry (overwritten by the CI pipeline). The site ran broken for 11 hours while engineers hand-crafted a fix forward.

## The lesson
Before any deploy, run the rollback path end-to-end in a staging environment that mirrors production. Confirm the previous image still exists in the registry. For schema migrations, write the down migration at the same time as the up migration — not afterward.

## Why it matters
An untested rollback is theater. When an incident is happening, stress is high, time is short, and a rollback that "should work" but hasn't been run will fail in unexpected ways, extending downtime.

## How to apply
- [ ] Write `down` migration immediately after writing `up` migration — same PR.
- [ ] Run `migrate down` then `migrate up` in the CI pipeline for every migration PR.
- [ ] Pin the N-1 image in your container registry; CI must not overwrite it until N+1 is proven stable.
- [ ] Include a rollback step in every deploy runbook; mark it as "verified" only after a dry run.
- [ ] Schedule quarterly rollback drills in production (with a maintenance window).

## Related
- `migrations-must-be-backward-compatible.md`
- `monitor-before-and-after-deploy.md`
- `write-the-runbook-before-the-incident.md`
