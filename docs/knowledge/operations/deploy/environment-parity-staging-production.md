# Environment Parity: Staging and Production

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A change passes all staging checks and breaks immediately
in production. Investigation reveals the staging Worker
was bound to a different KV namespace, an older D1 schema,
or a secret that resolves to a stub value — the staging
environment did not accurately mirror production.

## Context

Environment parity means staging and production are
identical in configuration and differ only in data volume
and traffic. Without parity, staging catches a different
class of bugs than production experiences, eroding trust
in the pre-production gate. On Cloudflare, parity has
four dimensions: Workers bindings, D1 schema state, R2
bucket policy, and Workers Secrets. Each must be managed
explicitly because they do not copy automatically when a
project is cloned or a new environment is provisioned.

## Worker Bindings in wrangler.toml Per Environment

Every binding must be declared for both environments.
An undeclared binding resolves to `undefined` at runtime,
not to an error at deploy time:

```toml
name = "myapp"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[env.staging]
[[env.staging.d1_databases]]
binding       = "DB"
database_name = "myapp-staging"
database_id   = "aaaa-staging-uuid"

[[env.staging.kv_namespaces]]
binding = "CACHE"
id      = "staging-kv-ns-id"

[env.production]
[[env.production.d1_databases]]
binding       = "DB"
database_name = "myapp-prod"
database_id   = "bbbb-prod-uuid"

[[env.production.kv_namespaces]]
binding = "CACHE"
id      = "prod-kv-ns-id"
```

Run a diff check in CI to catch binding drift:

```bash
# Extract and compare binding keys between envs
wrangler deploy --dry-run --env staging  --outdir /tmp/stg
wrangler deploy --dry-run --env production --outdir /tmp/prd
diff <(jq -r '.bindings[].name' /tmp/stg/index.js.map) \
     <(jq -r '.bindings[].name' /tmp/prd/index.js.map)
# Expected: no diff
```

## Seeded D1 State

Schema parity is necessary but not sufficient. Staging
should also carry a representative data seed so tests
exercise real foreign-key constraints and index paths:

```bash
# Snapshot production schema (no row data)
wrangler d1 export myapp-prod \
  --env production --no-data \
  --output prod-schema.sql

# Apply schema to staging and run seed script
wrangler d1 execute myapp-staging \
  --env staging --file prod-schema.sql
wrangler d1 execute myapp-staging \
  --env staging --file db/seeds/staging.sql
```

Run this reset at the start of every sprint so schema
drift is caught within days rather than weeks. Add both
migration applies as a PR check so mismatches block merge.

## R2 Bucket Separation

Never point a staging Worker at the production R2 bucket.
A staging bug that issues a `DeleteObject` will destroy
production assets. Maintain strict bucket separation:

| Resource       | Staging bucket            | Prod bucket         |
|----------------|---------------------------|---------------------|
| User uploads   | myapp-uploads-staging     | myapp-uploads-prod  |
| Static assets  | myapp-assets-staging      | myapp-assets-prod   |
| Export dumps   | myapp-exports-staging     | myapp-exports-prod  |

Sync a representative PII-stripped subset from production
to staging weekly with `rclone` rather than sharing the
bucket, so staging test data stays plausible.

## Secret Management with Workers Secrets

Secrets are per-environment and must be set explicitly
for each. A secret missing from staging silently becomes
`undefined` and causes runtime failures that look like
code bugs:

```bash
# Set secret for staging
echo "$STRIPE_KEY_TEST" | wrangler secret put STRIPE_KEY \
  --env staging

# Set secret for production
echo "$STRIPE_KEY_LIVE" | wrangler secret put STRIPE_KEY \
  --env production

# Verify secret is present (value is redacted)
wrangler secret list --env staging
wrangler secret list --env production
```

Commit a `secrets.inventory.txt` file (names only, no
values) to the repo. A CI job checks that every name in
the inventory is present in both environments via
`wrangler secret list`, and fails if any is missing.

## Common Staging/Production Divergence Causes

| Divergence            | How it hides              | Fix                      |
|-----------------------|---------------------------|--------------------------|
| Missing binding in    | `undefined` at runtime,   | Always declare both envs |
| staging wrangler.toml | not deploy-time error     | in wrangler.toml         |
| Stale D1 schema in    | Queries reference columns | Run schema sync weekly   |
| staging               | that don't exist in prod  |                          |
| Old compatibility_    | Different API surface;    | Pin same date in both    |
| date in staging       | subtle runtime diffs      | env blocks               |
| Secret only in prod   | `undefined` key; staging  | Inventory check in CI    |
|                       | works, prod explodes      |                          |
| Different zone/route  | Worker intercepts wrong   | Mirror routes in         |
| config                | paths in each env         | wrangler.toml exactly    |

## Anti-patterns

- Reusing production KV namespaces in staging — a staging
  cache-poisoning bug corrupts production reads.
- Manually patching staging schema without a migration
  file — the divergence is invisible until production
  receives the migration and breaks.
- Using stub secret values in staging (e.g. `"test"`) for
  secrets that are validated at startup — the validation
  passes a different path than production.
## Gotchas

- `wrangler.toml` `[vars]` block is checked into git and
  not suitable for secrets. Using it for a secret key
  exposes it in CI logs and git history.
- Workers routes configured in the Cloudflare dashboard
  are not reflected in `wrangler.toml`. Route divergence
  between environments must be audited separately.
- Cloudflare zone settings (min TLS version, security
  level, cache rules) are per-zone and are not captured
  in `wrangler.toml`. Use Terraform or the API to keep
  them in sync across staging and production zones.

## Verification

```bash
# Secret inventory must match across environments
wrangler secret list --env staging \
  | jq '[.[].name] | sort' > /tmp/stg-secrets.json
wrangler secret list --env production \
  | jq '[.[].name] | sort' > /tmp/prd-secrets.json
diff /tmp/stg-secrets.json /tmp/prd-secrets.json
# Expected: no diff
```

## Related

- `deploy/cloudflare-pages-preview-deployments.md`
- `deploy/zero-downtime-database-migrations.md`
- `deploy/feature-flag-deployment-decoupling.md`
- `infra/terraform-cloudflare-zone-config.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/workers/wrangler/environments/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/r2/buckets/
- https://developers.cloudflare.com/workers/configuration/environment-variables/
