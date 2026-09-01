# Workers Versioned Migrations Deployment Discipline

Schema migrations against databases reachable from Workers deserve the same rollout caution as code changes, because a Worker version and a migration bundle travel on separate tracks: the versioned deployment system can shift traffic by percentage, but a SQL migration executes the moment it is applied. Deployment discipline means sequencing those two tracks deliberately — apply backward-compatible schema first, upload and validate the Worker version second, then split traffic gradually — so that any version of the Worker can run against either schema state. This article records the workflow, controls, and evidence expectations for disciplined versioned deployments that carry migrations.

## Scope

Covers Workers deployments coordinated with D1 or SQL schema changes, using version upload/deploy separation, gradual traffic splitting, and rollback. Applies to teams using Wrangler-managed Workers where a migration step (D1 migrations, SQL DDL applied through an administrative path, or binding changes) accompanies a code release. Excludes static asset promotion pipelines, Queues consumer-only changes with no schema coupling, and emergency hotfixes governed by a separate break-glass procedure.

## Workflow or implementation guidance

1. Write the migration so it is additive and backward compatible: new nullable columns, new tables, or widened types only. Both the currently deployed Worker version and the candidate version must be able to read and write correctly with the post-migration schema.
2. Apply the migration to the target database ahead of the code release and confirm it completed. Record the migration version identifier and the timestamp.
3. Upload the new Worker code without deploying traffic: `wrangler versions upload`. This creates an immutable version with its own ID and preview URL but serves zero production traffic.
4. Exercise the preview URL against the migrated database with a smoke set that touches every changed schema object — read paths, write paths, and any prepared statements that name affected columns.
5. Begin a gradual deployment with a small initial split, for example `wrangler versions deploy --x-versions <candidate-id> --x-percentages 10`, keeping the remainder on the prior version.
6. Watch error rates, latency, and database-specific metrics for a soak period. Increase the split in steps (10 to 25 to 50 to 100) only after each interval is clean.
7. Promote the candidate to 100 percent and keep the previous version recorded for rollback.
8. Only after the new version has served full traffic reliably, schedule any destructive cleanup migration (dropping old columns, backfilling then tightening constraints) as its own separately reviewed change.

## Controls

- Migration compatibility review gate: a checklist item asserting dual-version compatibility (old code on new schema, new code on new schema) before upload.
- Version pinning control: production traffic percentages may only reference version IDs present in the deployment record; ad-hoc edits directly in code are prohibited.
- Split ceiling without approval: raising a gradual deployment beyond a defined threshold (for example 50 percent) requires a second reviewer.
- Rollback readiness check: the prior version ID is captured in the change ticket before the first split, so rollback is a single command rather than an investigation.
- Destructive-statement blocklist: `DROP`, `TRUNCATE`, and non-additive `ALTER` statements require explicit sign-off and cannot ride along with a feature deployment.
- Soak-time floor: a minimum dwell time at each split step before promotion, sized to the traffic pattern (at least one peak period for high-traffic Workers).

## Validation evidence

- The `wrangler versions list` output showing the candidate version ID, its upload timestamp, and the deployment pointing at it.
- Deployment detail (from `wrangler versions view <version-id>` or the dashboard) capturing the exact traffic percentages before and after each split change.
- Migration application log or database migration history table showing the applied version and timestamp preceding the version upload.
- Preview-URL smoke test transcript with per-endpoint results against the migrated schema.
- Error-rate and latency charts spanning the rollout window, annotated with the times of each split change.
- Rollback drill record (at least in a staging environment) demonstrating traffic returned to the prior version.

## Failure modes and correction

- Candidate version spikes errors at partial split: immediately redeploy the prior version to 100 percent using `wrangler versions deploy` with the old version ID, then diagnose via the preview URL against production-shaped data before re-attempting.
- Migration applied but upload fails or is cancelled: the schema is now ahead of code. This is safe only if the migration was additive; if not, restore from backup or apply a corrective migration before proceeding.
- Version skew across service bindings causes mixed-version requests: enable version affinity or a version override on the bound service so a request stays on one version for its whole trace.
- Split percentages edited via dashboard and Wrangler drift apart: reconcile by re-reading the deployment state, treating the API as the source of truth and recording the final state in the ticket.
- Rollback attempted on a version older than the retained window: gradual deployments can only reference recently uploaded versions; if the target has expired, redeploy the old code as a fresh upload rather than failing the rollback.

## Limitations

- Only a limited set of recently uploaded versions is available for gradual deployments and rollback; very old versions must be re-uploaded.
- Rollback reverts code, not schema: a destructive migration that already executed needs a forward-fix migration, not a version rollback.
- Gradual deployments split traffic at the edge without guaranteeing per-user stickiness unless version affinity or overrides are configured for service bindings.
- Durable Objects do not split traffic between versions in the same way; deployments involving them need the special handling described in the gradual deployments documentation.
- Soak evidence from low-traffic Workers may not surface rare-path errors; percentages alone are not proof of correctness.

## Canonical sources

- Cloudflare Workers docs, "Versions & deployments": https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Cloudflare Workers docs, "Gradual deployments": https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- Cloudflare Workers docs, "Rollbacks": https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/
- Cloudflare D1 docs, "Time Travel and backups": https://developers.cloudflare.com/d1/reference/time-travel/
