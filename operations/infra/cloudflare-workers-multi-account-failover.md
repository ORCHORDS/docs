# Cloudflare Workers Multi-Account Failover: Disaster Recovery Strategy

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

## Symptom

A Cloudflare account-level incident — not a data-centre outage but an account-layer event
such as a billing suspension, an abuse lock, an erroneous WAF global kill-switch, or a
compromised account credential that triggers an emergency freeze — takes all Workers, KV
namespaces, D1 databases, and R2 buckets for that account offline simultaneously. Standard
Cloudflare HA (multiple data centres, anycast routing) does not protect against account-layer
failures. RTO of hours while a support ticket works through the queue is unacceptable for
a production API.

## Context

Cloudflare's architecture separates the control plane (account, API tokens, dashboard) from
the data plane (edge nodes that serve Worker requests). When a control plane problem occurs,
the data plane may continue serving cached or previously deployed Workers for a window, but
any change — a rollback, a hotfix, an emergency deploy — becomes impossible. A multi-account
failover strategy keeps a warm secondary Cloudflare account with identical Worker code, its
own KV/D1/R2 state (or shared state via a neutral data layer), and DNS weights pre-configured
to shift traffic within minutes without touching the Cloudflare dashboard of the affected account.

This document covers the architecture, IaC setup, data synchronisation, and the runbook for
executing a failover.

---

## Section 1: Account Topology

Structure:
- **Primary account** (`cf-account-prod-a`): serves 100% of production traffic under normal
  conditions. Contains all production resources.
- **Secondary account** (`cf-account-prod-b`): warm standby, kept in sync. Under failover,
  receives 100% of traffic.
- **Ops account** (`cf-account-ops`): holds shared infrastructure — the DNS zone for the
  primary domain (critical: must NOT be on the primary account), audit logging Workers,
  and the Terraform state bucket.

DNS zone ownership is the most critical architectural decision. If the DNS zone lives on
`cf-account-prod-a` and that account is locked, you cannot redirect DNS records. The zone
must live on `cf-account-ops` or be delegated via external NS records to a registrar that
you control independently of any single Cloudflare account.

```
               ┌─────────────────────────────────┐
               │      cf-account-ops              │
               │  DNS zone: api.example.com       │
               │  Weight: A=100, B=0 (normal)     │
               │  WAF: global rules               │
               └──────────┬──────────┬────────────┘
                          │          │
                  ┌───────▼─┐    ┌───▼──────┐
                  │ Account A│    │Account B │
                  │ Primary  │    │Standby   │
                  │ Workers  │    │Workers   │
                  │ KV / D1  │    │KV / D1   │
                  │ R2 bucket│    │R2 bucket │
                  └──────────┘    └──────────┘
                          │          │
                     ┌────▼──────────▼────┐
                     │   Neutral data tier │
                     │  (PostgreSQL, Upstash│
                     │   Redis, Turso, etc) │
                     └────────────────────┘
```

---

## Section 2: Terraform IaC for Dual-Account Provisioning

Use Terraform workspaces or separate provider aliases for each account, sharing the same
module definitions.

```hcl
# providers.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  alias     = "primary"
  api_token = <redacted-secret>
}

provider "cloudflare" {
  alias     = "secondary"
  api_token = <redacted-secret>
}

provider "cloudflare" {
  alias     = "ops"
  api_token = <redacted-secret>
}
```

```hcl
# modules/worker-stack/main.tf
variable "account_id" {}
variable "worker_script_content" {}
variable "env_name" { default = "production" }

resource "cloudflare_worker_script" "api" {
  account_id = var.account_id
  name       = "api-worker-${var.env_name}"
  content    = var.worker_script_content

  plain_text_binding {
    name = "ENV"
    text = var.env_name
  }

  secret_text_binding {
    name = "DATABASE_URL"
    text = var.database_url
  }
}

resource "cloudflare_worker_route" "api" {
  zone_id     = var.zone_id
  pattern     = "api.example.com/*"
  script_name = cloudflare_worker_script.api.name
}
```

```hcl
# main.tf — instantiate the same module for both accounts
module "worker_primary" {
  source                = "./modules/worker-stack"
  providers             = { cloudflare = cloudflare.primary }
  account_id            = var.cf_account_id_primary
  zone_id               = var.cf_zone_id_ops
  worker_script_content = file("${path.module}/dist/worker.js")
  database_url          = var.database_url
}

module "worker_secondary" {
  source                = "./modules/worker-stack"
  providers             = { cloudflare = cloudflare.secondary }
  account_id            = var.cf_account_id_secondary
  zone_id               = var.cf_zone_id_ops
  worker_script_content = file("${path.module}/dist/worker.js")
  database_url          = var.database_url
}
```

Deploy both on every CI run. The secondary is always at parity with the primary.

---

## Section 3: DNS Failover Configuration

Use Cloudflare's **Load Balancer** (on the ops account zone) with origin pools pointing to
Worker routes on each account. Load Balancers survive account-level isolation of the backend
accounts because the balancer itself runs on the ops account.

```hcl
# DNS load balancer pointing to both Worker account routes
# Normal: Primary receives all traffic via weight=100/0
# Failover: Edit weights or disable primary pool via API

resource "cloudflare_load_balancer_pool" "primary" {
  provider   = cloudflare.ops
  account_id = var.cf_account_id_ops
  name       = "workers-primary"

  origins {
    name    = "account-a"
    address = "api-worker-production.account-a-subdomain.workers.dev"
    enabled = true
    weight  = 1
  }
}

resource "cloudflare_load_balancer_pool" "secondary" {
  provider   = cloudflare.ops
  account_id = var.cf_account_id_ops
  name       = "workers-secondary"

  origins {
    name    = "account-b"
    address = "api-worker-production.account-b-subdomain.workers.dev"
    enabled = true
    weight  = 1
  }
}

resource "cloudflare_load_balancer_monitor" "health" {
  provider       = cloudflare.ops
  account_id     = var.cf_account_id_ops
  type           = "https"
  path           = "/health"
  expected_codes = "200"
  interval       = 30
  timeout        = 10
  retries        = 2
}

resource "cloudflare_load_balancer" "api" {
  provider     = cloudflare.ops
  zone_id      = var.cf_zone_id_ops
  name         = "api.example.com"
  default_pool_ids = [cloudflare_load_balancer_pool.primary.id]
  fallback_pool_id = cloudflare_load_balancer_pool.secondary.id

  rules {
    name      = "primary-down-failover"
    condition = "health.pool == \"workers-primary\" && health.status == \"unhealthy\""

    fixed_response {
      # Not used; rule triggers failover to secondary pool
    }

    overrides {
      default_pools = [cloudflare_load_balancer_pool.secondary.id]
    }
  }
}
```

For manual failover, use the Cloudflare API (from the ops account token) to disable the
primary pool and force traffic to secondary within seconds — no dashboard login required on
the locked account.

---

## Section 4: Data Synchronisation Strategy

Workers state lives in KV, D1, and R2. Each requires a different sync strategy.

### KV Namespaces — Event-driven replication

KV does not have native cross-account replication. Use a Tail Worker to stream writes:

```typescript
// tail-worker/src/index.ts — attached to the primary Worker
export interface Env {
  SECONDARY_KV_ENDPOINT: string; // API endpoint on secondary account
  SECONDARY_API_TOKEN: string;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      if (event.event?.type !== 'kv-write') continue;
      // Replicate KV write to secondary account via API
      await fetch(`${env.SECONDARY_KV_ENDPOINT}/sync`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.SECONDARY_API_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(event.event),
      });
    }
  },
};
```

Alternatively, point both accounts at the same external KV-compatible store (Upstash Redis
with global replicas) and eliminate CF KV for anything that needs failover consistency.

### D1 — Logical replication via neutral PostgreSQL

D1 is SQLite-compatible but does not expose binlog or WAL streaming. For failover-critical
data, use a neutral PostgreSQL instance (Supabase, Neon, PlanetScale) as the primary data
store, and use D1 only as a read-through cache within each account.

```typescript
// Pattern: write to PostgreSQL, read from D1 cache with fallback to Postgres
export async function getUser(
  env: Env,
  userId: string
): Promise<User | null> {
  // Try D1 first (fast local read)
  const cached = await env.DB.prepare('SELECT * FROM users WHERE id = ?')
    .bind(userId)
    .first<User>();

  if (cached) return cached;

  // Fallback to neutral Postgres
  const user = await fetchFromPostgres(env.POSTGRES_URL, userId);
  if (user) {
    // Warm the D1 cache
    await env.DB.prepare('INSERT OR REPLACE INTO users VALUES (?, ?, ?)')
      .bind(user.id, user.name, user.email)
      .run();
  }
  return user;
}
```

### R2 — Bucket-level replication

Cloudflare R2 supports Cross-Bucket Replication (CBR) within an account but not cross-account
natively. Use `rclone` on a scheduled GitHub Actions job for cross-account R2 sync:

```yaml
# .github/workflows/r2-sync.yml
name: R2 cross-account sync

on:
  schedule:
    - cron: '*/15 * * * *'  # every 15 minutes

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Install rclone
        run: curl https://rclone.org/install.sh | sudo bash

      - name: Configure rclone
        run: |
          mkdir -p ~/.config/rclone
          cat > ~/.config/rclone/rclone.conf << EOF
          [r2-primary]
          type = s3
          provider = Cloudflare
          access_key_id = ${{ secrets.R2_PRIMARY_KEY }}
          secret_access_key = ${{ secrets.R2_PRIMARY_SECRET }}
          endpoint = https://${{ secrets.CF_ACCOUNT_ID_PRIMARY }}.r2.cloudflarestorage.com

          [r2-secondary]
          type = s3
          provider = Cloudflare
          access_key_id = ${{ secrets.R2_SECONDARY_KEY }}
          secret_access_key = ${{ secrets.R2_SECONDARY_SECRET }}
          endpoint = https://${{ secrets.CF_ACCOUNT_ID_SECONDARY }}.r2.cloudflarestorage.com
          EOF

      - name: Sync R2 buckets
        run: |
          rclone sync r2-primary:assets r2-secondary:assets \
            --transfers 32 \
            --checkers 32 \
            --checksum \
            --log-level INFO
```

---

## Section 5: Health Check Worker and Alert Integration

A canary Worker runs on the ops account and probes both primary and secondary endpoints:

```typescript
// health-monitor/src/index.ts — runs on cf-account-ops
export interface Env {
  PAGERDUTY_KEY: string;
  PRIMARY_URL: string;
  SECONDARY_URL: string;
}

async function probe(url: string, timeout = 5000): Promise<{ ok: boolean; latency: number }> {
  const start = Date.now();
  try {
    const res = await fetch(`${url}/health`, {
      signal: AbortSignal.timeout(timeout),
    });
    return { ok: res.status === 200, latency: Date.now() - start };
  } catch {
    return { ok: false, latency: Date.now() - start };
  }
}

export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const [primary, secondary] = await Promise.all([
      probe(env.PRIMARY_URL),
      probe(env.SECONDARY_URL),
    ]);

    console.log(JSON.stringify({ primary, secondary, ts: new Date().toISOString() }));

    if (!primary.ok) {
      await fetch('https://events.pagerduty.com/v2/enqueue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          routing_key: env.PAGERDUTY_KEY,
          event_action: 'trigger',
          payload: {
            summary: 'Cloudflare primary account Workers unhealthy — initiate failover',
            severity: 'critical',
            source: 'cloudflare-health-monitor',
            custom_details: { primary, secondary },
          },
        }),
      });
    }
  },
};
```

---

## Section 6: Failover Runbook

**RTO target: 5 minutes. RPO target: 15 minutes (RPO depends on data sync interval).**

```bash
#!/usr/bin/env bash
# failover.sh — run from ops account credentials
set -euo pipefail

OPS_TOKEN="${CF_OPS_TOKEN}"
OPS_ACCOUNT="${CF_ACCOUNT_ID_OPS}"
PRIMARY_POOL_ID="${LB_POOL_PRIMARY_ID}"
SECONDARY_POOL_ID="${LB_POOL_SECONDARY_ID}"
LB_ID="${LB_ID}"
ZONE_ID="${CF_ZONE_ID_OPS}"

echo "[$(date -u +%H:%M:%S)] Starting failover..."

# Step 1: Disable primary pool
curl -sf -X PATCH \
  "https://api.cloudflare.com/client/v4/accounts/$OPS_ACCOUNT/load_balancers/pools/$PRIMARY_POOL_ID" \
  -H "Authorization: Bearer $OPS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}' \
  | jq '.success'

echo "[$(date -u +%H:%M:%S)] Primary pool disabled. Verifying secondary receives traffic..."

sleep 30

# Step 2: Verify secondary is serving
STATUS=$(curl -sf "https://api.example.com/health" | jq -r '.account')
if [[ "$STATUS" != "secondary" ]]; then
  echo "ERROR: Expected secondary account but got: $STATUS"
  exit 1
fi

echo "[$(date -u +%H:%M:%S)] Failover complete. Secondary account serving production traffic."
echo "RUNBOOK: Open an incident in PagerDuty. Contact Cloudflare support for primary account recovery."
echo "RUNBOOK: When primary account is restored, run failback.sh after 30-minute soak period."
```

---

## Anti-Patterns

- **Keeping the DNS zone on the primary account** — this is the single most common mistake.
  If the primary account is locked, you cannot update DNS to redirect traffic.
- **Testing only the data plane** — probe the control plane too. Verify you can run
  `wrangler deploy` to the secondary account as part of your monthly DR drill.
- **Using the same API token for both accounts** — tokens are account-scoped. Each account
  needs its own token, stored in separate secrets.
- **Skipping data sync verification** — confirm the secondary D1 and KV actually contain
  recent data before declaring the failover strategy complete. A warm secondary with stale
  data is a false sense of security.
- **Long R2 sync intervals** — 15 minutes of R2 lag means 15 minutes of missing uploads
  post-failover. For critical media, use real-time replication via R2 event notifications
  to a Workers queue that mirrors writes.

---

## Gotchas

- Workers custom domains are zone-bound. If your Worker serves traffic on
  `api.example.com` via a custom domain binding in the primary account, that binding
  does not transfer during failover — traffic must be redirected at the DNS load-balancer
  level (on the ops account).
- Durable Objects in the primary account cannot be accessed from the secondary account.
  Any stateful data in DOs must be persisted to a neutral data store before being relied
  on in a failover.
- R2 pre-signed URLs include the account ID in the endpoint. Links shared before failover
  (`https://account-a-id.r2.cloudflarestorage.com/...`) continue to work as long as
  account A is accessible. After full account loss, those links are dead — serve assets
  through a Worker proxy that abstracts the account.
- Cloudflare support SLAs for account recovery are not guaranteed. Plan for hours to days,
  not minutes.

---

## Verification

```bash
# Monthly DR drill checklist

# 1. Confirm secondary Worker is at parity with primary
wrangler deployments list --env production --account-id $CF_ACCOUNT_ID_SECONDARY
# Compare version hash with primary

# 2. Send 1% of traffic to secondary and verify it serves correctly
# (Adjust LB weights: primary=99, secondary=1, monitor error rates)

# 3. Run failover.sh in --dry-run mode (add echo before curl calls)

# 4. Confirm R2 sync job ran within the last 15 minutes
gh run list --workflow r2-sync.yml --limit 5

# 5. Verify ops account API token can modify the load balancer
curl -sH "Authorization: Bearer $CF_OPS_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID_OPS/load_balancers" \
  | jq '.result | length'
```

---

## Related Articles

- `cloudflare-account-organization-team-access.md` — account boundary design
- `cloudflare-r2-backup-restore-strategy.md` — R2 backup patterns
- `disaster-recovery-rto-rpo.md` — RTO/RPO planning fundamentals
- `terraform-cloudflare-provider-workers-d1.md` — IaC for both accounts
- `cloudflare-workers-limits-resource-planning.md` — capacity constraints to plan for

---

## Sources

- Cloudflare Load Balancers: https://developers.cloudflare.com/load-balancing/
- Cloudflare R2 Cross-Bucket Replication: https://developers.cloudflare.com/r2/data-migration/
- rclone Cloudflare R2 backend: https://rclone.org/s3/#cloudflare-r2
- Cloudflare Workers health checks: https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- Cloudflare API load balancer endpoints: https://developers.cloudflare.com/api/operations/load-balancers-list-load-balancers
