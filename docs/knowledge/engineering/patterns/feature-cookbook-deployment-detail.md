# feature-cookbook-deployment-detail

**Issue:** Deployment — workers, D1, R2, KV, secrets
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy with `wrangler deploy`. The deploy fails. The
error is cryptic. You spend 30 minutes debugging. The
fix was a typo in wrangler.toml.

## Root cause
**Deployment is finicky.** Each CF resource has its own
config.

**Source:** CF Workers docs:
https://developers.cloudflare.com/workers/

## The "wrangler.toml" pattern

The wrangler.toml is the config:
```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-09"
compatibility_flags = ["nodejs_compat"]

# Variables
[vars]
ENVIRONMENT = "production"
LOG_LEVEL = "info"

# D1
[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "abc-123"
migrations_dir = "migrations"

# R2
[[r2_buckets]]
binding = "BUCKET"
bucket_name = "my-bucket"
preview_bucket_name = "my-bucket-preview"

# KV
[[kv_namespaces]]
binding = "KV"
id = "xyz-789"
preview_id = "xyz-789-preview"

# Durable Objects
[[durable_objects.bindings]]
name = "CHAT_ROOM"
class_name = "ChatRoom"

[[durable_objects.namespaces]]
namespace_id = "..."
class_name = "ChatRoom"

# Queues
[[queues.producers]]
binding = "EMAIL_QUEUE"
queue = "email-queue"

[[queues.consumers]]
queue = "email-queue"
max_batch_size = 10
max_batch_timeout = 30
max_retries = 5
dead_letter_queue = "email-dlq"

# Cron
[triggers]
crons = ["0 3 * * *"]

# Services
[[services]]
binding = "OTHER_SERVICE"
service = "other-worker"

# Analytics Engine
[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "my-analytics"

# Hyperdrive
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "..."

# Compatibility
node_compat = true
```

The wrangler.toml is the source of truth.

## The "secrets" pattern

For secrets, use `wrangler secret`:
```bash
wrangler secret put STRIPE_SECRET_KEY
wrangler secret put OPENAI_API_KEY
```

```ts
// In the Worker
const stripeKey = env.STRIPE_SECRET_KEY;
```

Secrets are encrypted; not in the repo.

## The "multi-environment" pattern

For multiple environments:
```toml
# wrangler.toml (default)
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-09"

# Default bindings
[[kv_namespaces]]
binding = "KV"
id = "dev-kv-id"

# Production
[env.production]
[[env.production.kv_namespaces]]
binding = "KV"
id = "prod-kv-id"

[[env.production.d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "prod-db-id"
```

```bash
# Deploy
wrangler deploy --env production
```

## The "preview environment" pattern

For PR previews:
```bash
PR_NUMBER=$(echo $GITHUB_REF | cut -d/ -f3)
ENV_NAME="pr-${PR_NUMBER}"
wrangler deploy --env "$ENV_NAME"
```

Each PR has a unique environment.

## The "deploy" pattern

For deploy:
```bash
# Build (if needed)
npm run build

# Run tests
npm test

# Lint
npm run lint

# Typecheck
npm run typecheck

# Deploy
wrangler deploy
```

The CI runs all checks before deploy.

## The "migrations" pattern

For D1 migrations:
```bash
# Apply to local dev
wrangler d1 migrations apply DB --local

# Apply to production
wrangler d1 migrations apply DB --remote
```

The migrations are versioned.

## The "tail" pattern

For real-time logs:
```bash
wrangler tail
```

The Worker logs are streamed to the terminal.

## The "rollback" pattern

For rollback:
```bash
# List versions
wrangler versions list

# Roll back
wrangler rollback --version-id abc-123
```

CF Workers has built-in rollback via versions.

## The "durable object migration" pattern

For DOs, you can't rename a class. Instead:
1. Create a new class with the new name
2. Update the binding to use the new class
3. Migrate the data (if needed)
4. Delete the old class

```toml
# New class
[[durable_objects.bindings]]
name = "CHAT_ROOM"
class_name = "ChatRoomV2"
```

The migration is a class rename.

## The "secrets rotation" pattern

For rotating secrets:
1. Generate a new secret
2. Add the new secret (dual-secret period)
3. Update the code to use the new secret
4. Remove the old secret

```bash
# 1. Add the new secret
echo "$NEW_STRIPE_KEY" | wrangler secret put STRIPE_SECRET_KEY_V2

# 2. Update the code
const stripeKey = env.STRIPE_SECRET_KEY_V2 ?? env.STRIPE_SECRET_KEY;

# 3. After verification, remove the old
wrangler secret delete STRIPE_SECRET_KEY
```

The dual-secret period allows verification.

## The "Workers Analytics Engine" pattern

For high-cardinality metrics:
```ts
env.ANALYTICS.writeDataPoint({
  blobs: [userId, action],
  doubles: [1],
  indexes: [tenantId],
});
```

The data is queryable via SQL.

## The "service binding" pattern

For Worker-to-Worker calls:
```ts
const response = await env.OTHER_SERVICE.fetch('https://other-service/api/...');
```

Service bindings are fast (no HTTP overhead).

## The "Pages + Worker" pattern

For Pages with a Worker function:
```
functions/
  api/
    users/
      [[path]].ts
  _middleware.ts
```

The functions are auto-routed.

## The "Workers Logs" pattern

For real-time logs in CF dashboard:
```ts
console.log({
  timestamp: new Date().toISOString(),
  level: 'info',
  message: 'user.login',
  userId: ctx.user.id,
});
```

The structured logs are in the CF dashboard.

## The "Logpush" pattern

For shipping logs:
```toml
[[unsafe.bindings]]
type = "logpush"
name = "LOG_DESTINATION"
destination = "r2"
dataset = "production_logs"
```

The logs are shipped to R2 / Datadog / Splunk.

## Verification
- **Test:** Deploy works
- **Live:** Smoke test passes
- **Audit:** Quarterly review of deploy process

## Gotchas
- **The "secret in wrangler.toml" anti-pattern.** Secrets
  must be encrypted; use `wrangler secret`.
- **The "same DB for dev and prod" anti-pattern.** Use
  different DBs for each environment.
- **The "no migrations" anti-pattern.** Schema changes
  without migrations break production.
- **The "no rollback plan" anti-pattern.** Always have a
  way to roll back.
- **The "deploy without testing" anti-pattern.** Always
  test in staging first.

## Related
- `safe-deploy-checklist.md`
- `cloudflare/workers-resource-limits.md`
- `cloudflare/d1-migration-best-practices.md`
- `feature-environment-promotion.md`
- `preview-environments.md`
- CF Workers: https://developers.cloudflare.com/workers/
- Wrangler: https://developers.cloudflare.com/workers/wrangler/
