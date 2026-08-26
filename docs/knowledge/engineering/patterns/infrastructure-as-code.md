# infrastructure-as-code

**Issue:** IaC for CF — wrangler, Terraform, Pulumi
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your CF account has 5 Workers, 3 D1 databases, 2 R2 buckets,
10 KV namespaces, 4 DOs. The configuration is in the CF
dashboard. A new engineer joins. They don't know what's
configured. They create a new Worker. They collide with an
existing one. They delete a namespace. The app is down.

## Root cause
**Dashboard config doesn't scale.** Click-ops is fine for 1
thing, painful for 10 things, impossible for 100 things.

**Source:** CF IaC:
https://developers.cloudflare.com/workers/wrangler/iac/

## The IaC tools for CF

### 1. Wrangler (CF native, declarative in wrangler.toml)
```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-09"

[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "xxxx-xxxx-xxxx-xxxx"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "prod-bucket"

[[kv_namespaces]]
binding = "KV"
id = "xxxx-xxxx-xxxx-xxxx"

[vars]
ENVIRONMENT = "production"
```

✅ **Native to CF** — first-class support
✅ **Free** — built into wrangler
✅ **Simple** — TOML is human-readable
❌ **Limited** — no loops, no conditionals, no composition
❌ **No state management** — separate from your infra state

### 2. Terraform (HashiCorp, the standard)
```hcl
# main.tf
resource "cloudflare_worker_script" "api" {
  name    = "my-api"
  content = file("./dist/index.js")

  plain_text_binding {
    name = "ENVIRONMENT"
    text = "production"
  }
}

resource "cloudflare_d1_database" "main" {
  name = "prod-db"
}

resource "cloudflare_r2_bucket" "main" {
  name = "prod-bucket"
}

resource "cloudflare_worker_route" "api_route" {
  zone_id     = var.cloudflare_zone_id
  pattern     = "api.example.com/*"
  script_name = cloudflare_worker_script.api.name
}
```

✅ **Mature** — battle-tested
✅ **Composable** — modules, loops, conditionals
✅ **State** — terraform.tfstate
❌ **Verbose** — more setup than wrangler
❌ **HCL** — not as nice as TypeScript/Python

### 3. Pulumi (TypeScript/Python/Go)
```ts
// index.ts
import * as cloudflare from '@pulumi/cloudflare';

const api = new cloudflare.WorkerScript('api', {
  name: 'my-api',
  content: require('fs').readFileSync('./dist/index.js', 'utf8'),
  bindings: {
    DB: { type: 'd1', id: db.id },
    BUCKET: { type: 'r2', id: bucket.id },
  },
});
```

✅ **TypeScript/Python** — same language as your app
✅ **Stateful** — pulumi state
✅ **Testable** — unit tests for infra
❌ **Newer** — less mature than Terraform
❌ **Smaller community** — fewer modules

## The decision matrix

| Need | Use |
|---|---|
| Simple Worker + bindings, small team | wrangler |
| Multi-env + multiple resources + CI/CD | Terraform |
| Same language as the app, complex logic | Pulumi |
| Existing Terraform expertise in the team | Terraform |

For most teams starting with CF, **wrangler + a few Terraform
modules for shared resources** is the right balance.

## The "multi-environment" pattern

For dev / staging / prod:
```toml
# wrangler.toml (shared)
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-09"

# wrangler.dev.toml
[env.dev]
name = "my-worker-dev"
[[env.dev.d1_databases]]
binding = "DB"
database_name = "dev-db"
database_id = "yyyy-yyyy-yyyy-yyyy"

# wrangler.staging.toml
[env.staging]
name = "my-worker-staging"
[[env.staging.d1_databases]]
binding = "DB"
database_name = "staging-db"
database_id = "zzzz-zzzz-zzzz-zzzz"

# wrangler.prod.toml
[env.production]
name = "my-worker-production"
[[env.production.d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "xxxx-xxxx-xxxx-xxxx"
```

Deploy with:
```bash
wrangler deploy --env dev
wrangler deploy --env staging
wrangler deploy --env production
```

## The "preview environment" pattern

For PR previews, create a unique environment per PR:
```bash
PR_NUMBER=$(echo $GITHUB_REF | cut -d/ -f3)
ENV_NAME="pr-${PR_NUMBER}"
wrangler deploy --env "$ENV_NAME" --var PR_NUMBER:$PR_NUMBER
```

The Worker is deployed to `pr-123.example.com`. Reviewers
can see the changes live.

## The "D1 migration" pattern

D1 migrations should be in code:
```sql
-- migrations/0001_initial.sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE
);
```

```json
// wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "xxxx"
migrations_dir = "migrations"
```

Apply migrations:
```bash
wrangler d1 migrations apply DB --env production
```

Migrations are versioned, ordered, and tested in CI.

## The "secrets" pattern

Secrets should NOT be in wrangler.toml. Use `wrangler secret`:
```bash
echo "sk-..." | wrangler secret put OPENAI_API_KEY --env production
```

The secret is encrypted at rest. The wrangler.toml only has
binding references, not values.

## Verification
- **Test:** `test/iac.test.ts > every resource defined in
  wrangler.toml exists in CF` — passes
- **Live:** IaC diff is reviewed before apply
- **Audit:** Quarterly review of IaC vs actual state

## Gotchas
- **Wrangler has no state.** If you delete wrangler.toml, the
  resources stay. To delete, you must delete them via
  wrangler or the dashboard.
- **Terraform can drift.** If someone changes the dashboard,
  the Terraform state is stale. Run `terraform plan` before
  every apply.
- **Pulumi is more flexible but more dangerous.** You can do
  more, but you can also do more wrong. Use a linter
  (`pulumi policy`).
- **CF resources are not all in IaC.** Some features (WAF
  rules, page rules, rate limits) are only in the dashboard
  or via the API. Document the gap.
- **The IaC is in your repo.** If the repo is public, your
  config is public. Don't put secrets in the repo.
- **The state file** (Terraform .tfstate) is sensitive. It
  contains all your resource IDs + outputs. Use a remote
  state backend (Terraform Cloud, S3 with encryption).

## Related
- `feature-environment-promotion.md`
- `preview-environments.md`
- `zero-downtime-deploys.md`
- `secrets-rotation-runbook.md`
- CF IaC: https://developers.cloudflare.com/workers/wrangler/iac/
- Terraform CF provider: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs
- Pulumi CF: https://www.pulumi.com/registry/packages/cloudflare/
