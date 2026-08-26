# Terraform Cloudflare Workers Runtime Version Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker deployed months ago suddenly behaves differently after Cloudflare advances the
default runtime to a newer V8/workerd version. Or your CI pipeline fails a
`terraform plan` because the `compatibility_date` field was left unset and Cloudflare now
requires one. You need a systematic way to pin, audit, and advance runtime versions across
many Worker scripts without manual dashboard edits.

## Context

Every Cloudflare Worker has two runtime knobs:

| Field | Purpose | Default behaviour |
|---|---|---|
| `compatibility_date` | Pins the "behavioural snapshot" of the Workers runtime (JS APIs, `fetch` semantics, KV behaviour, etc.) | If omitted, Cloudflare uses its internal default — may change silently |
| `compatibility_flags` | Opt-in or opt-out of specific runtime behaviours ahead of (or behind) their scheduled date | `[]` |

`compatibility_date` uses `YYYY-MM-DD` strings. Advancing the date exposes your Worker to
all runtime changes between the old date and the new date simultaneously — Cloudflare
publishes a changelog at https://developers.cloudflare.com/workers/configuration/compatibility-dates/.

Terraform manages these fields on `cloudflare_worker_script.compatibility_date` and
`cloudflare_worker_script.compatibility_flags`. The goal is to manage them as code so
that date bumps go through PR review and CI validation.

---

## Section 1 — Single Worker with Pinned Compatibility Date

```hcl
# terraform/worker.tf

variable "workers_compatibility_date" {
  type        = string
  description = "Compatibility date for all Workers in this stack. Advance deliberately after testing."
  default     = "2026-01-01"

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", var.workers_compatibility_date))
    error_message = "Must be an ISO date string: YYYY-MM-DD."
  }
}

variable "workers_compatibility_flags" {
  type        = list(string)
  description = "Opt-in compatibility flags for all Workers."
  default     = []
}

resource "cloudflare_worker_script" "api" {
  account_id = var.cloudflare_account_id
  name       = "api-worker"
  content    = file("${path.module}/../../dist/worker.js")

  compatibility_date  = var.workers_compatibility_date
  compatibility_flags = var.workers_compatibility_flags

  # Node.js compatibility layer (optional)
  # compatibility_flags = ["nodejs_compat"]
}
```

---

## Section 2 — Multiple Workers with Per-Worker Date Overrides

Not all Workers can advance to the same compatibility date simultaneously. Use a local
map to express per-Worker overrides while keeping a sane default.

```hcl
# terraform/workers_versions.tf

locals {
  default_compat_date = "2026-01-01"

  workers = {
    "api-worker" = {
      script      = "dist/api-worker.js"
      compat_date = "2026-06-01"              # Advanced: verified against changelog
      compat_flags = ["nodejs_compat"]
    }
    "webhook-worker" = {
      script      = "dist/webhook-worker.js"
      compat_date = local.default_compat_date  # Pinned; needs audit before advancing
      compat_flags = []
    }
    "image-resize-worker" = {
      script      = "dist/image-resize.js"
      compat_date = "2025-09-15"              # Intentionally older; uses legacy crypto API
      compat_flags = ["formdata_parser_supports_files"]
    }
  }
}

resource "cloudflare_worker_script" "workers" {
  for_each = local.workers

  account_id          = var.cloudflare_account_id
  name                = each.key
  content             = file("${path.module}/../../${each.value.script}")
  compatibility_date  = each.value.compat_date
  compatibility_flags = each.value.compat_flags
}
```

---

## Section 3 — Compatibility Flag Reference via Terraform Output

Expose current version pins as Terraform outputs for audit dashboards or Datadog annotations.

```hcl
# terraform/outputs.tf

output "worker_compatibility_matrix" {
  description = "Current compatibility dates and flags per Worker script"
  value = {
    for name, script in cloudflare_worker_script.workers :
    name => {
      compatibility_date  = script.compatibility_date
      compatibility_flags = script.compatibility_flags
    }
  }
}
```

```bash
# In CI, export to JSON and diff against last release
terraform output -json worker_compatibility_matrix > /tmp/compat-matrix-current.json
diff /tmp/compat-matrix-baseline.json /tmp/compat-matrix-current.json
```

---

## Section 4 — Node.js Compatibility Layer

```hcl
# terraform/nodejs_compat.tf

# Workers that use Node.js built-ins (path, crypto, buffer, stream, etc.)
# require the nodejs_compat flag. Without it, `import { createHash } from 'node:crypto'`
# throws at runtime.

resource "cloudflare_worker_script" "nodejs_worker" {
  account_id = var.cloudflare_account_id
  name       = "nodejs-compat-worker"
  content    = file("${path.module}/../../dist/nodejs-worker.js")

  compatibility_date  = "2024-09-23"   # Minimum date for full nodejs_compat v2 support
  compatibility_flags = ["nodejs_compat"]

  # If you need both old Node.js compat and new WHATWG streams:
  # compatibility_flags = ["nodejs_compat", "streams_enable_constructors"]
}
```

---

## Section 5 — Advance Compatibility Date Safely in TypeScript CI Script

Before bumping `compatibility_date` in Terraform, validate the Worker against the new
date in a preview deployment.

```typescript
// scripts/compat-date-preview.ts
// Deploys a canary Worker with the new compat date and runs smoke tests.

const WORKER_NAME = "api-worker-compat-canary";
const NEW_COMPAT_DATE = process.env.NEW_COMPAT_DATE ?? "";
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID ?? "";
const CF_API_TOKEN = process.env.CF_API_TOKEN ?? "";

if (!NEW_COMPAT_DATE.match(/^\d{4}-\d{2}-\d{2}$/)) {
  console.error("Set NEW_COMPAT_DATE env var (YYYY-MM-DD)");
  process.exit(1);
}

async function deployCanary(scriptContent: string): Promise<{ id: string }> {
  const formData = new FormData();
  formData.append(
    "metadata",
    new Blob(
      [JSON.stringify({ compatibility_date: NEW_COMPAT_DATE, main_module: "worker.js" })],
      { type: "application/json" }
    )
  );
  formData.append("worker.js", new Blob([scriptContent], { type: "application/javascript+module" }));

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}`,
    {
      method: "PUT",
      headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
      body: formData,
    }
  );

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Deploy failed: ${resp.status} — ${err}`);
  }
  return (await resp.json()) as { id: string };
}

async function smokeTest(workerUrl: string): Promise<void> {
  const checks = [
    { path: "/health", expectedStatus: 200 },
    { path: "/api/v1/ping", expectedStatus: 200 },
  ];

  for (const check of checks) {
    const r = await fetch(`${workerUrl}${check.path}`);
    if (r.status !== check.expectedStatus) {
      throw new Error(`Smoke test FAILED: ${check.path} returned ${r.status}, expected ${check.expectedStatus}`);
    }
  }
  console.log("All smoke tests passed with compat date", NEW_COMPAT_DATE);
}

const script = await Bun.file("dist/worker.js").text();
await deployCanary(script);
await smokeTest(`https://${WORKER_NAME}.${CF_ACCOUNT_ID}.workers.dev`);
console.log(`Canary passed — safe to set compatibility_date = "${NEW_COMPAT_DATE}" in Terraform.`);
```

---

## Section 6 — Alerting When Workers Fall Behind the Changelog

```typescript
// worker/src/compat-audit.ts
// Run as a scheduled Worker (weekly cron) to detect stale compat dates.

const STALENESS_THRESHOLD_DAYS = 365;  // Alert if compat date is > 1 year behind today

interface WorkerScript {
  id: string;
  compatibility_date: string | null;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(auditCompatDates(env));
  },
};

async function auditCompatDates(env: Env): Promise<void> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/workers/scripts`,
    { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
  );
  const { result } = (await resp.json()) as { result: WorkerScript[] };

  const now = Date.now();
  const stale = result.filter(w => {
    if (!w.compatibility_date) return true;  // No date set = stale
    const age = (now - new Date(w.compatibility_date).getTime()) / 86_400_000;
    return age > STALENESS_THRESHOLD_DAYS;
  });

  if (stale.length > 0) {
    const msg = stale.map(w => `${w.id}: ${w.compatibility_date ?? "NOT SET"}`).join("\n");
    console.warn("[COMPAT AUDIT] Stale Workers:\n" + msg);
    await env.SLACK_WEBHOOK.fetch(new Request(env.SLACK_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: `*Workers Compatibility Date Audit*\n${stale.length} Worker(s) have a stale or missing compatibility date:\n\`\`\`${msg}\`\`\``,
      }),
    }));
  } else {
    console.log("[COMPAT AUDIT] All Workers have recent compatibility dates.");
  }
}
```

---

## Anti-patterns

- **Omitting `compatibility_date` entirely** — Workers without a date inherit Cloudflare's
  internal default, which advances silently. Always set an explicit date.
- **Setting all Workers to `today`** — the latest compatibility date may include breaking
  changes from rulesets published days ago. Use a date at least 2 weeks in the past so
  it appears in the published changelog before you adopt it.
- **Advancing the date by months in one PR** — multiple changelog entries land simultaneously.
  Advance in incremental steps (quarterly or per breaking change).
- **Using `nodejs_compat` without understanding the polyfill overhead** — the Node.js
  compat layer increases bundle size. Audit `wrangler build --outdir dist` bundle size
  before and after enabling the flag.

---

## Gotchas

- `compatibility_flags` are **additive** to the `compatibility_date` behaviour snapshot.
  A flag that opts IN to a behaviour that is already default on the compat date is a
  no-op but does not error.
- The `nodejs_compat` flag has two versions: the original (pre-2024-09-23 compat date)
  and v2 (post). v2 is activated automatically when `compatibility_date >= 2024-09-23`;
  you cannot use v1 on a newer date.
- Terraform does not validate that the `compatibility_date` is in the Cloudflare-published
  changelog. An invalid or future date silently defaults to the last known date.
- `for_each` on `cloudflare_worker_script` means renaming a Worker key in the map destroys
  the old script and creates a new one — this causes a brief deployment gap. Use a blue/green
  approach with traffic routing for zero-downtime compat date advances on critical Workers.
- The Cloudflare Terraform provider does not expose `compatibility_date` as a computed
  attribute if it is not set in state — run `terraform refresh` after a manual dashboard
  change to sync.

---

## Verification

```bash
# List all Worker scripts with their compat dates (requires CF API token)
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts" \
  | jq '.result[] | {id, compatibility_date, compatibility_flags}'

# Check a specific Worker's current compat date
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/api-worker" \
  | jq '.result | {name: .id, compatibility_date, compatibility_flags}'

# Terraform plan diff showing compat date changes
terraform plan -var="workers_compatibility_date=2026-06-01" | grep -A3 "compatibility_date"

# Validate Node.js compat flag is effective
wrangler dev --compatibility-date 2024-09-23 --compatibility-flags nodejs_compat
```

---

## Related

- `wrangler-toml-multi-environment-config.md`
- `workers-cold-start-bundle-size-optimization.md`
- `cloudflare-workers-limits-resource-planning.md`
- `terraform-cloudflare-workers-routes-zone-config.md`
- `workers-dora-deployment-frequency-metrics.md`

---

## Sources

- Cloudflare Docs — Compatibility Dates: https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- Cloudflare Docs — Compatibility Flags: https://developers.cloudflare.com/workers/configuration/compatibility-flags/
- Cloudflare Docs — Node.js Compatibility: https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- Terraform cloudflare_worker_script: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_script
- Cloudflare Changelog — Workers Runtime Releases: https://developers.cloudflare.com/workers/platform/changelog/
