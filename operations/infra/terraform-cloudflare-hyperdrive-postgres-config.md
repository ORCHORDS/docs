# Terraform Cloudflare Hyperdrive Postgres Config

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project Workers need to query a managed PostgreSQL database (Supabase or Neon) for user
profiles, post metadata, and follow-graph queries. Establishing a fresh TCP connection and
TLS handshake from a Worker on every request is expensive — Workers run across hundreds of
Cloudflare PoPs, each creating independent connections that overwhelm the database's max
connection limit. Hyperdrive solves this by maintaining persistent, pooled connections at
the Cloudflare network edge, but configuring it manually per environment creates drift between
staging and production connection strings.

## Context

Cloudflare Hyperdrive is a connection pooling and query caching proxy that sits between Workers
and external databases. The Terraform provider (`cloudflare/cloudflare` ≥ 4.36) exposes
`cloudflare_hyperdrive_config` which manages the Hyperdrive configuration including the
database connection string, caching policy, and binding name. The connection string contains
credentials and must be treated as a sensitive value throughout the Terraform lifecycle.

## Resource Definition — cloudflare_hyperdrive_config

Each `cloudflare_hyperdrive_config` maps to one Hyperdrive instance. example project runs separate
instances for the primary read-write connection and a read-replica connection.

```hcl
variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare account that owns the Hyperdrive instance"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "PostgreSQL password for the example project_app database user"
}

variable "db_host" {
  type        = string
  description = "PostgreSQL host (e.g. db.project.supabase.co)"
}

variable "db_port" {
  type    = number
  default = 5432
}

resource "cloudflare_hyperdrive_config" "primary" {
  account_id = var.cloudflare_account_id
  name       = "example project-primary-db"

  origin {
    database = "example project_production"
    host     = var.db_host
    port     = var.db_port
    scheme   = "postgres"
    user     = "example project_app"
    password = <redacted-secret>
  }

  caching {
    disabled               = false
    max_age                = 60     # seconds; tune per query volatility
    stale_while_revalidate = 15
  }
}

resource "cloudflare_hyperdrive_config" "replica" {
  account_id = var.cloudflare_account_id
  name       = "example project-replica-db"

  origin {
    database = "example project_production"
    host     = var.db_replica_host
    port     = var.db_port
    scheme   = "postgres"
    user     = "example project_readonly"
    password = <redacted-secret>
  }

  caching {
    disabled               = false
    max_age                = 120   # longer cache for read-heavy replica queries
    stale_while_revalidate = 30
  }
}
```

## Configuration — Worker Script with Hyperdrive Binding

The Hyperdrive config ID is bound to a Worker as a `hyperdrive_config_binding`. The Worker
uses the binding's `.connectionString` property to construct a standard `postgres://` URL
for the `pg` or `postgres.js` library.

```hcl
resource "cloudflare_worker_script" "api" {
  account_id = var.cloudflare_account_id
  name       = "example project-api"
  content    = file("${path.module}/dist/api.js")

  compatibility_date  = "2025-09-01"
  compatibility_flags = ["nodejs_compat"]

  hyperdrive_config_binding {
    binding = "DB"       # env.DB.connectionString in the Worker
    id      = cloudflare_hyperdrive_config.primary.id
  }

  hyperdrive_config_binding {
    binding = "DB_REPLICA"
    id      = cloudflare_hyperdrive_config.replica.id
  }
}
```

Worker code pattern using `postgres.js`:

```javascript
import postgres from "postgres";

export default {
  async fetch(request, env) {
    // env.DB.connectionString is injected by Hyperdrive at runtime
    const sql = postgres(env.DB.connectionString, {
      max: 5,
      idle_timeout: 20,
    });
    const [user] = await sql`SELECT id, username FROM users WHERE id = ${userId}`;
    await sql.end();
    return Response.json(user);
  }
};
```

## CI Integration — Sensitive Variable Handling

Never store connection strings in Terraform state unencrypted. Use Terraform Cloud or an
S3 backend with KMS, and pass the password via an environment variable in CI.

```yaml
# .github/workflows/hyperdrive-deploy.yml
name: Deploy Hyperdrive Config

on:
  push:
    branches: [main]
    paths: ["infra/hyperdrive/**"]

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Terraform Init (S3 backend)
        working-directory: infra/hyperdrive
        run: terraform init
        env:
          AWS_ACCESS_KEY_ID:     ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}

      - name: Terraform Apply
        working-directory: infra/hyperdrive
        run: terraform apply -auto-approve
        env:
          CLOUDFLARE_API_TOKEN:        ${{ secrets.CF_API_TOKEN }}
          TF_VAR_cloudflare_account_id: ${{ secrets.CF_ACCOUNT_ID }}
          TF_VAR_db_host:              ${{ secrets.DB_HOST }}
          TF_VAR_db_password:          ${{ secrets.DB_PASSWORD }}
          TF_VAR_db_replica_host:      ${{ secrets.DB_REPLICA_HOST }}
          TF_VAR_db_replica_password:  ${{ secrets.DB_REPLICA_PASSWORD }}
```

```hcl
# backend.tf
terraform {
  backend "s3" {
    bucket         = "example project-terraform-state"
    key            = "hyperdrive/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:us-east-1:123456789:key/example project-state-key"
    dynamodb_table = "example project-terraform-locks"
  }
}
```

## Outputs — Hyperdrive IDs for Cross-Stack References

```hcl
output "hyperdrive_primary_id" {
  value       = cloudflare_hyperdrive_config.primary.id
  description = "Hyperdrive config ID for the primary database — use as Worker binding ID"
}

output "hyperdrive_replica_id" {
  value       = cloudflare_hyperdrive_config.replica.id
  description = "Hyperdrive config ID for the read replica"
}
```

Downstream stacks (e.g., a separate Workers module) consume these via `terraform_remote_state`
or a data source rather than duplicating the connection string.

## Anti-patterns

- Storing the full `postgres://user:password@host/db` connection string as a `plain_text_binding`
  on the Worker — it appears in the Worker bundle and in Cloudflare's API response plaintext;
  use `hyperdrive_config_binding` which keeps credentials server-side.
- Setting `caching.disabled = true` globally — this eliminates the main latency benefit of
  Hyperdrive for read-heavy anonymous social feeds; only disable caching for write endpoints.
- Using the same Hyperdrive config for staging and production — a staging misconfiguration
  can drain the production connection pool; maintain separate Hyperdrive configs per environment.
- Skipping `compatibility_flags = ["nodejs_compat"]` — the `pg` and `postgres.js` libraries
  require Node.js compatibility mode; without it they fail to import with a `require is not defined`
  error.
- Setting `max_age` to 0 to be "safe" on read endpoints — this disables caching and forces
  Hyperdrive to hit the database on every Worker invocation, eliminating the pooling benefit.

## Gotchas

- Hyperdrive does not support prepared statement caching between connections; use parameterised
  queries for correctness but do not expect query plan reuse from the pool.
- Updating `origin.password` in Terraform triggers a Hyperdrive config replacement (destroy +
  create), briefly disrupting Workers that hold open connections during the transition.
- The Cloudflare API masks `origin.password` in GET responses — Terraform detects this as a
  perpetual diff unless you add `lifecycle { ignore_changes = [origin.password] }` after the
  initial apply and rotate passwords out-of-band.
- Hyperdrive supports PostgreSQL 14+ only; MySQL and SQLite are not supported.
- Free and Workers Paid plan accounts have a limit of 5 Hyperdrive configs per account as of
  mid-2026 — plan your primary/replica/staging/analytics configs accordingly.

## Verification

```bash
# List Hyperdrive configs and confirm names/IDs
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/hyperdrive/configs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {id, name, origin: .origin | {host, database, port}}'

# Confirm Worker has the Hyperdrive binding
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/example project-api/bindings" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | select(.type=="hyperdrive")'

# Smoke-test via the Worker's health endpoint
curl -s https://example.com/api/health | jq .db_ping_ms
```

## Related

- `hyperdrive-postgresql-pulumi-iac.md` — Pulumi equivalent for Hyperdrive provisioning
- `postgresql-connection-pooling-pgbouncer.md` — PgBouncer as an alternative to Hyperdrive for non-edge deployments
- `terraform-cloudflare-provider-workers-d1.md` — D1 as an alternative for edge-native SQL
- `cloudflare-workers-limits-resource-planning.md` — Worker CPU/memory limits when running DB queries

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/hyperdrive_config
- https://developers.cloudflare.com/hyperdrive/configuration/
- https://developers.cloudflare.com/hyperdrive/get-started/
- https://developers.cloudflare.com/workers/databases/connecting-to-databases/
