# Rollback Strategies for Workers and Pages

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A broken deploy is live in production. Error rates spike,
on-call is paged, and the team needs to restore service
in the least time possible without compounding the
incident by making additional untested changes.

## Context

Cloudflare Workers and Pages have different rollback
mechanics, and the stateful layers (D1, KV, R2) impose
hard constraints on what "rollback" can actually mean.
Code rollback is instant; data rollback is often
impossible. The safest approach is to design deploys
so code rollback is always safe regardless of data state,
which means following expand-contract for schema changes
and treating KV/R2 writes as append-only where possible.

## Workers Gradual Rollout and Traffic Splitting

Workers Versions let you split traffic between two
versions without touching DNS or a load balancer:

```bash
# Deploy the new version without sending it traffic yet
wrangler versions upload --env production
# Note the VERSION_ID printed in the output

# Split traffic: 10 % to new version, 90 % to current
wrangler versions deploy \
  --version <NEW_VERSION_ID>=10 \
  --version <CURRENT_VERSION_ID>=90 \
  --env production
```

Monitor error rates at 10 %. If stable, increase
to 50 → 100. If errors appear, shift traffic back:

```bash
# Instant rollback: 100 % to previous version
wrangler versions deploy \
  --version <CURRENT_VERSION_ID>=100 \
  --env production
```

The rollback takes effect globally in seconds. No cold
start penalty — the previous version's isolates are
still warm on edge nodes.

## Instant Rollback to a Previous Deployment

For a full-replacement (non-gradual) deploy, roll back
to any previous deployment by version ID:

```bash
# List recent deployments
wrangler deployments list --env production

# Roll back to a specific version
wrangler rollback <VERSION_ID> --env production
```

For Pages:

```bash
# List deployments for the project
wrangler pages deployment list --project-name myapp

# Roll back Pages to a specific deployment ID
wrangler pages deployment rollback \
  --project-name myapp <DEPLOYMENT_ID>
```

Pages rollback is also available in the dashboard:
Deployments tab → find the target deploy → "Rollback
to this deployment". The rollback completes in under
30 seconds for most projects.

## D1 Migration Rollback

D1 does not support transactional DDL rollback across
deployed statements. The expand-contract pattern makes
this safe: because the code that ran during phase 1
(expand) is still valid against the phase-3 (contract)
schema, rolling back the Worker code never leaves the
database in an inconsistent state.

If a migration was applied in error before contract:

```bash
# Manually reverse a non-destructive expand migration
wrangler d1 execute myapp-db --env production \
  --command "ALTER TABLE users DROP COLUMN display_name;"

# Remove the tracking row so the migration re-runs
# if you re-apply it later
wrangler d1 execute myapp-db --env production \
  --command "DELETE FROM d1_migrations
             WHERE name = '0012_add_display_name.sql';"
```

Never manually reverse a migration that has already had
data written to the new column by production traffic.
Treat that as a forward-only migration and write a new
migration that corrects the data.

## KV and R2 Data Rollback: What Is Not Possible

| Layer | Code rollback | Data rollback         |
|-------|---------------|-----------------------|
| Worker| Yes, instant  | n/a (stateless)       |
| D1    | Yes (expand-  | Schema: manual DDL    |
|       | contract)     | Rows: point-in-time*  |
| KV    | Yes           | No — no versioning    |
| R2    | Yes           | Object versioning opt-|
|       |               | in per bucket only    |

KV does not retain previous values. Once a key is
overwritten the old value is gone. Design KV writes as
append-only (e.g. write to `flags/<version>/key` rather
than overwriting `flags/key`) if you need rollback.

R2 object versioning must be enabled before an incident,
not during one:

```bash
wrangler r2 bucket update myapp-assets \
  --versioning enabled
```

With versioning on, restore a previous object version via
the S3-compatible `CopyObject` API, specifying the target
`versionId` as the copy source.

## Incident Response Checklist for a Broken Deploy

Use this sequence when error rates spike after a deploy:

1. **Confirm the deploy caused it.** Correlate the error
   spike with the deployment timestamp in Workers metrics.
2. **Roll back code immediately.**
   `wrangler rollback <PREV_VERSION_ID> --env production`
3. **Verify rollback is effective.** Watch the error rate
   drop on the Workers Analytics dashboard (allow 60 s).
4. **Check for data side-effects.** If the broken version
   wrote to D1 or KV, confirm the writes are safe against
   the old Worker code before declaring recovery.
5. **Do not re-deploy the fix under pressure.** Reproduce
   the failure in a preview environment first, then ship.

## Anti-patterns

- Rolling forward with a hot-fix under pressure — a
  second bad deploy during an incident doubles downtime.
- Expecting `wrangler rollback` to undo D1 data changes —
  it only changes the active Worker version.
- Enabling R2 versioning after an object is corrupted
  rather than proactively before the incident.
- Not keeping the previous three Workers version IDs
  accessible in the deploy runbook.

## Gotchas

- `wrangler rollback` without a version ID rolls back to
  the immediately previous version, not to the last known
  good version if multiple deploys happened rapidly.
- Workers gradual rollout percentages must sum to 100.
  Omitting a version ID from the `--version` flags causes
  the remaining traffic to be unrouted (502 errors).
- Pages rollback via the dashboard does not trigger the
  `deployment_status` GitHub webhook, so automated post-
  deploy checks will not fire for the rolled-back version.

## Verification

```bash
# Confirm the active version after rollback
wrangler deployments list --env production | head -3
# The rolled-back version ID should appear as "Active"
```

## Related

- `deploy/zero-downtime-database-migrations.md`
- `deploy/feature-flag-deployment-decoupling.md`
- `deploy/cloudflare-workers-deploy-pipeline.md`
- `monitoring/error-rate-alerting.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://developers.cloudflare.com/pages/platform/deployments/
- https://developers.cloudflare.com/r2/buckets/object-versioning/
