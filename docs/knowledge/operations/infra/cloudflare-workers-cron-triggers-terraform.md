# Cloudflare Workers Cron Triggers with Terraform

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need a Cloudflare Worker to run on a schedule (database cleanup, cache warm-up, periodic report
generation, heartbeat checks) without an external cron host. Wrangler's `[triggers]` block works for
one environment, but multi-environment promotion through Terraform requires cron schedules to be
declared as IaC alongside the Worker binding so that staging and production each carry their own cadence.

## Context

Cloudflare Workers support up to three cron expressions per Worker script. The runtime invokes the
Worker's `scheduled` handler with a `ScheduledEvent` that carries `scheduledTime` (Unix ms) and
`cron` (the matched expression). Terraform's `cloudflare_workers_cron_trigger` resource binds
expressions to a named Worker script. Because cron triggers are zone-independent, they attach to the
account level — the `zone_id` field is absent; only `account_id` and `script_name` are required.

Key constraints:
- Maximum 3 cron expressions per Worker.
- Minimum interval is 1 minute (`* * * * *`).
- `wrangler.toml` cron entries and Terraform must not conflict; prefer one source of truth.
- Cron triggers only fire in production; local `wrangler dev` does not simulate them.

## TypeScript Worker Handler

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  ENVIRONMENT: string;
}

export default {
  // HTTP handler still required even for cron-only workers
  async fetch(_req: Request, _env: Env): Promise<Response> {
    return new Response("cron worker – no HTTP interface", { status: 404 });
  },

  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(dispatch(event.cron, env));
  },
};

async function dispatch(cron: string, env: Env): Promise<void> {
  switch (cron) {
    case "0 * * * *":      // top of every hour
      await purgeExpiredSessions(env.DB);
      break;
    case "0 4 * * *":      // 04:00 UTC daily
      await rebuildKVSummary(env.DB, env.KV);
      break;
    case "*/5 * * * *":    // every 5 minutes
      await heartbeat(env.ENVIRONMENT);
      break;
    default:
      console.warn(`unhandled cron expression: ${cron}`);
  }
}

async function purgeExpiredSessions(db: D1Database): Promise<void> {
  const result = await db
    .prepare("DELETE FROM sessions WHERE expires_at < ?")
    .bind(Date.now())
    .run();
  console.log(`purged ${result.meta.changes} expired sessions`);
}

async function rebuildKVSummary(db: D1Database, kv: KVNamespace): Promise<void> {
  const { results } = await db
    .prepare("SELECT org_id, COUNT(*) AS cnt FROM events GROUP BY org_id")
    .all<{ org_id: string; cnt: number }>();
  for (const row of results) {
    await kv.put(`summary:${row.org_id}`, String(row.cnt), { expirationTtl: 86400 });
  }
  console.log(`rebuilt KV summaries for ${results.length} orgs`);
}

async function heartbeat(env: string): Promise<void> {
  const url = `https://status.example.com/ping/${env}`;
  const resp = await fetch(url, { method: "POST" });
  if (!resp.ok) console.error(`heartbeat failed: ${resp.status}`);
}
```

## Terraform Resource

```hcl
# terraform/modules/cron-worker/main.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

variable "account_id"   { type = string }
variable "environment"  { type = string }  # "staging" | "production"
variable "script_name"  { type = string }  # matches wrangler name field

locals {
  # Staging runs less frequently to reduce D1 costs
  schedules = var.environment == "production" ? [
    "0 * * * *",   # hourly session purge
    "0 4 * * *",   # daily KV rebuild
    "*/5 * * * *", # 5-minute heartbeat
  ] : [
    "0 * * * *",   # hourly session purge (staging mirrors prod)
    "0 6 * * *",   # offset daily rebuild to avoid slot contention
  ]
}

resource "cloudflare_workers_cron_trigger" "scheduled" {
  account_id  = var.account_id
  script_name = var.script_name
  schedules   = local.schedules
}
```

```hcl
# terraform/envs/production/main.tf
module "cron_worker" {
  source      = "../../modules/cron-worker"
  account_id  = var.cloudflare_account_id
  environment = "production"
  script_name = "orchords-cron-worker"
}
```

## GitHub Actions Deployment

```yaml
# .github/workflows/deploy-cron-worker.yml
name: Deploy Cron Worker

on:
  push:
    branches: [main]
    paths:
      - "workers/cron/**"
      - "terraform/modules/cron-worker/**"

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"

      - run: npm ci
        working-directory: workers/cron

      - name: Deploy Worker script via Wrangler
        run: npx wrangler deploy --env production
        working-directory: workers/cron
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Apply cron trigger via Terraform
        working-directory: terraform/envs/production
        run: |
          terraform init
          terraform apply -auto-approve \
            -var="cloudflare_account_id=${{ secrets.CF_ACCOUNT_ID }}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Observability: Tail Worker for Cron Events

```typescript
// src/tail.ts – attach as a tail consumer to capture cron outcomes
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      if (event.scriptTrigger?.type !== "scheduled") continue;
      const outcome = event.outcome; // "ok" | "exception" | "exceeded-cpu" | "canceled"
      const cron    = event.scriptTrigger.scheduledTime;
      await env.KV.put(
        `cron:last-run:${cron}`,
        JSON.stringify({ outcome, ts: Date.now() }),
        { expirationTtl: 604800 },
      );
      if (outcome !== "ok") {
        console.error(`Cron job ${cron} finished with outcome: ${outcome}`);
      }
    }
  },
};
```

## Anti-patterns

- **Dual ownership**: defining schedules in both `wrangler.toml` and Terraform leads to Terraform
  perpetually overwriting wrangler's changes on each `apply`. Pick one — IaC teams should own cron
  in Terraform and remove `[triggers]` from wrangler.toml entirely.
- **Skipping `ctx.waitUntil`**: without it the Worker runtime may terminate before async DB writes
  complete, silently truncating work.
- **Using cron for real-time workloads**: minimum 1-minute granularity means cron is unsuitable
  for sub-minute scheduling; use Durable Object alarms instead.
- **Hardcoding cron strings in the handler**: the `dispatch` switch must match the Terraform
  `schedules` list exactly; drift silently drops tasks.

## Gotchas

- `cloudflare_workers_cron_trigger` replaces the entire schedule list on every `apply`; partial
  updates are not possible — always provide the complete set.
- Cron triggers respect the account-level CPU time limit (10 ms unbound for free, 30 s for paid),
  not the fetch handler's 50 ms default.
- Time zones: all cron expressions are evaluated in UTC; there is no zone-aware override.
- If the Worker script does not exist yet, the Terraform resource will 404 — deploy the script
  first, then apply the trigger resource.

## Verification

```bash
# List current schedules via API
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/orchords-cron-worker/schedules" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.schedules'

# Trigger a manual execution (test cron path)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/orchords-cron-worker/triggers" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method":"scheduled","cron":"0 * * * *"}'

# Confirm last-run KV key written by tail worker
npx wrangler kv key get "cron:last-run:$(date -u +%s)" --namespace-id $KV_NS_ID
```

## Related

- `cloudflare-durable-objects-stateful-edge.md` — sub-minute scheduling via DO alarms
- `terraform-cloudflare-provider-workers-d1.md` — D1 binding provisioning
- `workers-opentelemetry-tail-workers.md` — tail worker observability patterns
- `pulumi-cloudflare-workers-infrastructure-as-code.md` — Pulumi alternative for Worker IaC
- `cloudflare-workers-limits-resource-planning.md` — CPU and memory constraints

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_cron_trigger
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://developers.cloudflare.com/workers/observability/tail-workers/
