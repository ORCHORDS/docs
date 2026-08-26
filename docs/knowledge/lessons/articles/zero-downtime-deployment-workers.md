# Zero-Downtime Deployment Lessons from Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A new Worker version is deployed to production on a Friday afternoon. The deployment
completes in under 10 seconds — global propagation to Cloudflare's edge. Within two
minutes, error rates spike: the new Worker is incompatible with a schema migration that
was deployed to D1 an hour earlier but whose Durable Object migration path assumed the old
Worker would still be running. Requests in flight at the PoP level hit both the old and new
Worker simultaneously during the propagation window.

The team assumed "deploy Workers = instant and safe." The real lesson: deployment speed
does not equal deployment safety. Zero-downtime is a design constraint, not an automatic
property of the platform.

## Context

Cloudflare Workers deployments propagate globally within seconds. This is a competitive
advantage and a new failure mode. Traditional deployment strategies (blue-green, canary
with weighted load balancers) were designed for minutes-long deploy windows with explicit
traffic shifting. Workers operates differently:

- No server fleet to drain
- No "warm up" period; Workers cold-start latency is sub-millisecond for most scripts
- Global propagation is not instantaneous — it can take 10-60 seconds for all PoPs to
  converge on the new version
- During propagation, different PoPs serve different versions simultaneously
- Wrangler's `--rollback` is fast but not atomic; rollback also propagates over the same
  window

Understanding this model is the precondition for designing zero-downtime deployments on
Workers.

## Strategy 1 — Decouple Schema and Code Deploys

The most common cause of downtime during Workers deploys is a mismatch between the code
version and the data schema version. The safe pattern:

1. **Deploy the schema change first** in a backward-compatible way (add a column, don't
   rename it; add an optional field, don't remove a required one)
2. **Deploy the Worker code** that can handle both old and new schema
3. **Deploy the cleanup** (remove the old column/field) only after the new Worker has
   been fully propagated and all traffic is confirmed on the new version

This three-phase deploy adds calendar time but eliminates the overlap hazard. For D1
schema changes, use `wrangler d1 migrations apply` with a migration file that is
explicitly backward-compatible and verified against the previous Worker version.

## Strategy 2 — Canary Deployments with Workers Gradual Rollouts

Cloudflare Workers supports percentage-based traffic splitting via `wrangler deploy
--percentage` in combination with a named version. This enables true canary deploys:

1. Deploy new version to 5% of traffic with `--percentage 5`
2. Monitor error rate, CPU time, and custom metrics via Workers Analytics Engine for
   15-30 minutes
3. Promote to 25%, 50%, 100% with explicit verification gates between each step

Key implementation details:
- Requests from the same client will NOT be consistently routed to the same version unless
  you use a sticky session cookie or Durable Object binding to pin the version
- The percentage is applied at the PoP level, not the user level, so the same user may
  hit different versions on successive requests during a canary window
- Log the Worker version ID (available as `env.__CF_VERSION_METADATA__` in recent runtimes)
  on every request to trace which version handled each error

Never run a canary below 5% for longer than one hour — the statistical signal is too weak
to detect errors that affect less than 0.1% of requests before the window passes.

## Strategy 3 — Durable Object Migration Safety

Durable Objects are the stateful layer most likely to cause downtime during a Worker deploy.
Their migration path requires explicit care:

- **Never rename a Durable Object class** in a deploy that also changes its logic. Rename
  in one deploy (new name, same logic), verify all objects are migrated, then change logic
  in a second deploy.
- **Use the `new_sqlite_classes` / `renamed_classes` migration declaration** in
  `wrangler.toml` and verify the migration runs correctly in a staging environment against
  a representative data volume before production.
- **Drain in-flight requests before upgrading a DO**: set a flag in KV or the DO's own
  storage that causes the DO to reject new requests (return 503) for 30 seconds before
  upgrading, allowing in-flight transactions to complete.
- **Test the rollback path**: deploy the old Worker version and verify DOs remain
  accessible. Some schema changes to SQLite-backed DOs are not reversible without data
  export/re-import.

## Strategy 4 — Feature Flags as a Deployment Gate

Zero-downtime is easier when the new behavior is deployed but inactive. Use a feature flag
(KV, a simple Worker binding, or a third-party flag service) to separate deploy from
release:

1. Deploy the new code with the feature behind a flag
2. Enable the flag for internal users / a small percentage of production traffic
3. Verify correct behavior end-to-end
4. Flip the flag to 100%
5. Remove the flag on the next cleanup deploy

Workers KV is well-suited for feature flags: it is globally readable, has sub-millisecond
read latency at edge, and values can be updated without a Worker re-deploy. Cache TTL
should be set to 30-60 seconds for flags (not the default 60 minutes) so that a flag
change propagates quickly in an incident.

## Strategy 5 — Health Checks and Automated Rollback

Workers does not have a built-in automated rollback trigger. Implement one:

1. Deploy new Worker version
2. A separate monitoring Worker or external probe hits a `/health` endpoint every 30
   seconds and compares error rate and p99 latency against a 7-day baseline
3. If error rate exceeds a threshold (e.g., 1% above baseline) for two consecutive checks,
   trigger a `wrangler rollback` via a Cloudflare API call from a CI/CD pipeline

The rollback mechanism itself must be tested at least once per quarter. The first time a
team discovers their rollback script is broken should not be during an incident.

Emit a `deployment.version` metric tag on every request via Workers Analytics Engine so
that rollback verification is a simple dashboard check: error rate drops when version
reverts.

## Anti-patterns

**Treating Workers deploy as a single atomic event.** The global propagation window means
multiple versions serve simultaneously. Design for this; do not pretend it does not happen.

**Coupling database migration to application deploy in a single pipeline step.** If the
pipeline runs the D1 migration and then immediately deploys the Worker, the new schema is
live before the new code that handles it finishes propagating. Decouple them with an
explicit gate between steps.

**Using `wrangler deploy --dry-run` as a staging environment.** Dry-run validates the
bundle but does not test bindings, D1 queries, or DO behavior. Maintain a real staging
Worker with its own D1 database, KV namespaces, and DO instances.

**Skipping the canary for "small" changes.** Configuration-only changes (a changed default
value, a flag removal) have caused production incidents as often as feature changes. All
deploys go through the same promotion process.

**Not versioning the Worker in logs.** Without the version in every log line or analytics
event, it is impossible to correlate an error spike with the specific deploy that caused it
when multiple versions are propagating simultaneously.

## Gotchas

- **KV write propagation is eventual.** A feature flag written to KV may not be visible at
  all PoPs for up to 60 seconds (up to the cache TTL). A Worker reading a flag immediately
  after it is written may see the old value. Design rollout gates that tolerate this window.

- **`wrangler rollback` reverts to the previous published version, not any version.** If
  you have deployed v3, v2, and v1 in succession, `wrangler rollback` goes to v2, not v1.
  To revert to an arbitrary older version, use `wrangler deploy` with a saved bundle or a
  Git-tagged Wrangler configuration.

- **Free tier CPU limits reset per request, not globally.** A Worker that is within limits
  on average can still be killed for exceeding 10ms CPU on a single request. Canary traffic
  does not protect you from per-request CPU budget issues; you must test with realistic
  request payloads.

- **Scheduled Workers (Cron Triggers) are not gradual.** Cron Triggers fire on the new
  version immediately after the deploy propagates. If a scheduled job and an API Worker
  must be on the same version simultaneously, deploy the API Worker first, wait for full
  propagation, then deploy the Cron Trigger Worker.

- **`nodejs_compat` flag changes are not backward-compatible.** Adding or removing the
  Node.js compatibility flag between deploys can change how modules resolve. Test in staging
  before production.

## Verification

After every production deploy:

- [ ] Deployment version tag is visible in Workers Analytics Engine within 5 minutes
- [ ] Error rate on the new version is within 0.5% of baseline at 5-minute mark
- [ ] p99 latency on the new version is within 20% of baseline at 5-minute mark
- [ ] D1 query error rate is zero for all migrations applied in this deploy
- [ ] Feature flags for new behavior are confirmed in expected state via KV read
- [ ] Rollback procedure was tested in staging within the last 30 days

## Related

- `always-test-rollback-before-deploying.md`
- `rollback-is-a-tested-release-path.md`
- `feature-flag-lifecycle-management.md`
- `staging-prod-parity-lies-config-drift-data-volume.md`
- `workers-testing-miniflare-vitest.md`
- `cloudflare-storage-primitive-selection.md`

## Sources

- Cloudflare Workers Gradual Deployments documentation
- Cloudflare Durable Objects migration documentation (wrangler.toml `migrations` key)
- Cloudflare Workers Analytics Engine documentation
- Wrangler CLI changelog — rollback and versioning commands
- Cloudflare Workers Limits documentation (CPU time, KV eventual consistency)
