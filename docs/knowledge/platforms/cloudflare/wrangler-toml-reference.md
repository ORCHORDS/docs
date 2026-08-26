# wrangler-toml-reference

**Issue:** wrangler.toml configuration for Pages Functions — bindings, compatibility, environments
**Date:** 2026-08-11
**Status:** documented

## Minimal wrangler.toml for Pages Functions

```toml
name = "my-app"
compatibility_date = "2024-01-01"
pages_build_output_dir = "dist"

# D1 database binding
[[d1_databases]]
binding = "DB"
database_name = "my-app-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# KV namespace binding
[[kv_namespaces]]
binding = "SESSIONS"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[kv_namespaces]]
binding = "RATE_LIMIT"
id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

# Environment variables (non-secret)
[vars]
ENVIRONMENT = "production"
APP_URL = "https://app.example.com"
```

## Secret variables

Secrets are NOT in wrangler.toml. Add them via CLI or dashboard:

```bash
wrangler pages secret put WEBHOOK_SECRET
wrangler pages secret put JWT_SECRET
```

Access in Workers as `env.WEBHOOK_SECRET` (typed as `string | undefined` with strict types).

## Multiple environments

```toml
# Default / production
[env.production]
name = "my-app"
vars = { ENVIRONMENT = "production", APP_URL = "https://app.example.com" }

[[env.production.d1_databases]]
binding = "DB"
database_name = "my-app-prod"
database_id = "prod-db-id-here"

# Staging
[env.staging]
name = "my-app-staging"
vars = { ENVIRONMENT = "staging", APP_URL = "https://staging.example.com" }

[[env.staging.d1_databases]]
binding = "DB"
database_name = "my-app-staging"
database_id = "staging-db-id-here"
```

Deploy: `wrangler pages deploy --env staging`

## Compatibility flags

```toml
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]
```

`nodejs_compat` enables Node.js compatibility layer — adds `Buffer`, `process.env`, etc.
Use only if a dependency requires it. Without it, Workers is leaner (smaller bundle, faster cold start).

## R2 binding

```toml
[[r2_buckets]]
binding = "ASSETS"
bucket_name = "my-app-assets"
```

## Service bindings (Worker-to-Worker)

```toml
[[services]]
binding = "AUTH_WORKER"
service = "my-auth-worker"
entrypoint = "AuthHandler"
```

## Queue bindings (producers + consumers)

```toml
[[queues.producers]]
binding = "EMAIL_QUEUE"
queue = "email-notifications"

[[queues.consumers]]
queue = "email-notifications"
max_batch_size = 10
max_batch_timeout = 5
```

## Typescript Env interface

Your `Env` interface must match wrangler.toml bindings exactly. With `@cloudflare/workers-types`:

```typescript
// functions/_lib/types.ts
export interface Env {
  // D1 bindings:
  DB?: D1Database;

  // KV bindings:
  SESSIONS?: KVNamespace;
  RATE_LIMIT?: KVNamespace;

  // R2 bindings:
  ASSETS?: R2Bucket;

  // Environment variables (always string in env):
  ENVIRONMENT?: string;
  APP_URL?: string;

  // Secrets (same type as env vars):
  WEBHOOK_SECRET?: string;
  JWT_SECRET?: string;
}
```

All bindings are optional (`?`) because they may be absent in local dev or test environments.

## Local development

```bash
wrangler pages dev dist --d1=DB:my-app-local --kv=SESSIONS:sessions-local
```

Or use `wrangler.dev.toml` overrides. D1 local databases are created automatically on first run.

## Gotchas

- **`database_id` is different from `database_name`**: Use `wrangler d1 list` to get the UUID.
- **`binding` name is case-sensitive**: `DB` in toml must match `env.DB` in TypeScript exactly.
- **Pages vs Workers**: `pages_build_output_dir` is Pages-specific. For standalone Workers, use `main` instead.
- **Secrets not in toml**: Never put secrets in wrangler.toml — they're committed to git. Use `wrangler pages secret put`.
- **compatibility_date**: Advancing this can enable breaking changes. Test in staging before bumping production.
- **Multiple KV namespaces**: Each KV namespace needs a separate `[[kv_namespaces]]` block with a unique `binding` name. Don't reuse one namespace for different concerns.

## Related

- `workers-types-migration.md`
- `pages-functions-env-types.md`
- `d1-typescript-patterns.md`
- `kv-rate-limiting.md`
- `session-management-workers.md`
