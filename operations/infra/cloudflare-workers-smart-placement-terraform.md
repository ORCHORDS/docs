# Cloudflare Workers Smart Placement Terraform

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Workers deployed to the nearest PoP often experience higher latency when the
Worker makes many subrequests to an origin database or upstream API that is
geographically concentrated (e.g. a D1 database pinned to WEUR, a Hyperdrive
pool pointing to a Frankfurt PostgreSQL cluster).  Cloudflare's Smart Placement
feature automatically shifts Worker execution to the PoP closest to the
back-end, reducing round-trip latency by 40-70 % in measured cases.  Managing
Smart Placement through the dashboard creates configuration drift; Terraform or
Pulumi must own the setting.

## Context

Smart Placement (`placement.mode = "smart"`) instructs Cloudflare's scheduling
system to analyse the Worker's subrequest patterns over a 24-hour window and
migrate execution to the optimal colo.  It is mutually exclusive with
`placement.mode = "off"` (default).  The feature is supported on:
- `cloudflare_worker_script` (Terraform provider >= 4.28)
- `cloudflare.WorkerScript` (Pulumi cloudflare provider >= 5.2)
- `wrangler.toml` (`[placement] mode = "smart"`)

Smart Placement is not available on Workers that use `cron` triggers only, or
Workers running in `no_bundle` compatibility mode.

---

## 1. Terraform — Enabling Smart Placement on a Worker Script

```hcl
# infra/workers_smart_placement.tf

resource "cloudflare_worker_script" "api_worker" {
  account_id = var.cloudflare_account_id
  name       = "example project-api-worker"
  content    = file("${path.module}/../dist/worker.js")
  module     = true

  placement {
    mode = "smart"
  }

  # Hyperdrive binding pointing to WEUR PostgreSQL cluster
  hyperdrive_config_binding {
    name       = "DB"
    binding    = cloudflare_hyperdrive_config.pg_weur.id
  }

  compatibility_date  = "2025-09-01"
  compatibility_flags = ["nodejs_compat"]
}
```

---

## 2. Terraform — Smart Placement + Custom Domain Route

```hcl
resource "cloudflare_worker_route" "api_route" {
  zone_id     = var.zone_id
  pattern     = "api.example.com/*"
  script_name = cloudflare_worker_script.api_worker.name
}

# Smart Placement is set on the script; routes inherit the setting automatically.
# No additional route-level configuration is required.
```

---

## 3. Pulumi TypeScript — Smart Placement

```typescript
// infra/workerSmartPlacement.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as fs from "fs";

const apiWorker = new cloudflare.WorkerScript("example project-api-worker", {
  accountId: accountId,
  name:      "example project-api-worker",
  content:   fs.readFileSync("../dist/worker.js", "utf8"),
  module:    true,
  placement: {
    mode: "smart",
  },
  hyperdriveConfigBindings: [{
    name:    "DB",
    binding: hyperdriveConfig.id,
  }],
  compatibilityDate:  "2025-09-01",
  compatibilityFlags: ["nodejs_compat"],
});

export const workerName = apiWorker.name;
```

---

## 4. `wrangler.toml` Equivalent (for local development awareness)

```toml
# wrangler.toml
name = "example project-api-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]

[placement]
mode = "smart"

[[hyperdrive]]
binding = "DB"
id      = "abc123hyperdriveid"
```

Wrangler ignores `[placement]` during local `wrangler dev` — it only takes
effect after `wrangler deploy`.  IaC (Terraform/Pulumi) is the authoritative
source; `wrangler.toml` should mirror it for developer awareness.

---

## 5. Observability — Confirming Smart Placement is Active

```typescript
// src/index.ts — log the colo handling the request
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cf = request.cf as CfProperties | undefined;
    console.log({
      colo:       cf?.colo,          // PoP handling the request
      tlsCipher:  cf?.tlsCipher,
      country:    cf?.country,
    });
    // ... handler logic
  },
};
```

```bash
# Tail live logs to observe colo distribution after enabling Smart Placement
wrangler tail example project-api-worker --format json | \
  jq 'select(.logs[].message[0].colo != null) | .logs[].message[0].colo'
```

Compare the modal colo in logs before and after enabling Smart Placement; it
should shift toward the colo nearest your Hyperdrive/D1 back-end.

---

## 6. Disabling Smart Placement Selectively

```hcl
# For a Worker that serves only static cached responses — Smart Placement wastes
# scheduling overhead. Explicitly set mode = "off".
resource "cloudflare_worker_script" "static_worker" {
  account_id = var.cloudflare_account_id
  name       = "example project-static-worker"
  content    = file("${path.module}/../dist/static.js")
  module     = true

  placement {
    mode = "off"
  }
}
```

---

## Anti-patterns

- Do not enable Smart Placement on a Worker that primarily serves cached
  responses with no origin calls — the scheduler has no signal to optimise on
  and the feature adds overhead without benefit.
- Do not mix `wrangler deploy` (which reads `wrangler.toml`) and Terraform for
  the same Worker script — they will overwrite each other's placement setting.
  Pick one deployment path.
- Do not assume Smart Placement is immediate; the optimiser requires ~24 hours
  of traffic before migrating execution.  Latency measurements taken within the
  first few hours after enabling will not reflect steady-state behaviour.

## Gotchas

- Smart Placement is not supported on Workers using `Service Worker` format
  (non-module scripts).  Ensure `module = true` in HCL or `format = "modules"`
  in `wrangler.toml`.
- The Terraform provider returns `placement {}` as an empty block if the API
  returns mode `"off"` — this may cause a perpetual diff if your HCL explicitly
  sets `mode = "off"`.  Use `lifecycle { ignore_changes = [placement] }` if the
  setting is managed externally.
- Smart Placement interacts with Durable Objects: if a Worker calls a DO stub,
  the DO's location (not the back-end origin) becomes the placement signal.

## Verification

```bash
# Check placement mode via Cloudflare API
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/example project-api-worker/settings" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" | jq '.result.placement'
# Expected: {"mode": "smart"}

# Terraform plan should show no changes after apply
terraform plan -target=cloudflare_worker_script.api_worker
# Expected: No changes. Infrastructure is up-to-date.
```

## Related

- `terraform-cloudflare-workers-routes-zone-config.md`
- `terraform-cloudflare-workers-custom-domain-routing.md`
- `hyperdrive-postgresql-pulumi-iac.md`
- `terraform-cloudflare-hyperdrive-postgres-config.md`
- `cloudflare-durable-objects-stateful-edge.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/smart-placement/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_script
- https://www.pulumi.com/registry/packages/cloudflare/api-docs/workerscript/
