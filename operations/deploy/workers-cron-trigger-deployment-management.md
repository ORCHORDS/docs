# Workers Cron Trigger Deployment Management

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A scheduled Workers cron job fires mid-deployment while the new Worker
version is partially routed, causing it to run against an incompatible D1
schema. After wrangler promotes the new version the old cron schedule is
silently orphaned because `wrangler.toml` removed a trigger that was still
present in the Cloudflare dashboard.

## Context

Cloudflare Workers cron triggers are defined in `wrangler.toml` under
`[triggers]` and deployed alongside the Worker. Unlike HTTP handlers, cron
triggers fire asynchronously on Cloudflare's scheduler, meaning a newly
deployed version may receive a cron invocation before readiness checks pass.
The Cloudflare API lists active crons separately from the Worker bundle, so
dashboard-created crons can diverge from `wrangler.toml`. Managing crons as
code, disabling them during risky migrations, and reconciling dashboard state
are the three pillars of safe cron deployment.

## Pinning Cron Definitions in wrangler.toml

All cron triggers must live in `wrangler.toml` — never created manually in
the dashboard — so that `wrangler deploy` is the single source of truth.

```toml
# wrangler.toml
name = "billing-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[env.production]
vars = { ENVIRONMENT = "production" }

[[env.production.triggers.crons]]
crons = [
  "0 2 * * *",   # daily ledger reconcile at 02:00 UTC
  "*/15 * * * *" # heartbeat every 15 minutes
]

[env.staging]
vars = { ENVIRONMENT = "staging" }

[[env.staging.triggers.crons]]
crons = ["0 6 * * *"]  # staging runs once per day at 06:00 UTC
```

## Disabling Crons During Risky Migrations

Before a D1 schema migration that adds NOT NULL columns, disable cron
triggers by deploying a version with an empty cron list, run the migration,
then restore the schedule.

```typescript
// scripts/cron-guard.ts
import { execSync } from "child_process";
import Cloudflare from "cloudflare";

const cf = new Cloudflare({ apiToken: process.env.CLOUDFLARE_API_TOKEN });

async function disableCrons(accountId: string, workerName: string) {
  const worker = await cf.workers.scripts.schedules.update(
    workerName,
    { schedules: [] },  // empty array clears all cron triggers
    { account_id: accountId }
  );
  console.log("Crons disabled:", JSON.stringify(worker));
}

async function restoreCrons(
  accountId: string,
  workerName: string,
  schedules: Array<{ cron: string }>
) {
  const worker = await cf.workers.scripts.schedules.update(
    workerName,
    { schedules },
    { account_id: accountId }
  );
  console.log("Crons restored:", JSON.stringify(worker));
}

// Usage in migration pipeline
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const WORKER = "billing-worker";

await disableCrons(ACCOUNT_ID, WORKER);
execSync("npx wrangler d1 migrations apply DB --env production --remote", {
  stdio: "inherit",
});
await restoreCrons(ACCOUNT_ID, WORKER, [
  { cron: "0 2 * * *" },
  { cron: "*/15 * * * *" },
]);
```

## Reconciling Dashboard State Against wrangler.toml

A CI job that diffs live cron state against declared state catches drift
introduced by manual dashboard edits before it causes an outage.

```typescript
// scripts/reconcile-crons.ts
import Cloudflare from "cloudflare";

interface CronExpectation {
  cron: string;
}

const DECLARED: CronExpectation[] = [
  { cron: "0 2 * * *" },
  { cron: "*/15 * * * *" },
];

async function reconcile() {
  const cf = new Cloudflare({ apiToken: process.env.CLOUDFLARE_API_TOKEN! });
  const accountId = process.env.CLOUDFLARE_ACCOUNT_ID!;

  const live = await cf.workers.scripts.schedules.get("billing-worker", {
    account_id: accountId,
  });

  const liveSet = new Set(live.schedules?.map((s) => s.cron) ?? []);
  const declaredSet = new Set(DECLARED.map((d) => d.cron));

  const orphaned = [...liveSet].filter((c) => !declaredSet.has(c));
  const missing = [...declaredSet].filter((c) => !liveSet.has(c));

  if (orphaned.length > 0) {
    console.error("CRON DRIFT — orphaned triggers:", orphaned);
    process.exit(1);
  }
  if (missing.length > 0) {
    console.error("CRON DRIFT — missing triggers:", missing);
    process.exit(1);
  }
  console.log("Cron state is consistent.");
}

reconcile();
```

```yaml
# .github/workflows/cron-reconcile.yml
name: Cron Reconcile
on:
  schedule:
    - cron: "0 * * * *"  # run hourly
  workflow_dispatch:

jobs:
  reconcile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci
      - run: npx tsx scripts/reconcile-crons.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

## Anti-patterns

- Creating cron triggers manually in the Cloudflare dashboard instead of
  `wrangler.toml`; they survive `wrangler deploy` and run against the new
  Worker version unexpectedly.
- Running cron-guarded D1 schema migrations without first verifying the
  cron was actually disabled via the API; the `wrangler deploy` step and the
  schedule disable are independent calls.
- Using the same cron schedule in staging and production without environment
  guards, causing staging jobs to mutate production D1 databases when env
  vars are mis-set.

## Gotchas

- `wrangler deploy` does NOT remove dashboard-only crons that are absent
  from `wrangler.toml`; it only adds/updates the ones listed. Use the API
  to clear all schedules before redeploying if a full reconcile is needed.
- Cron invocations that start within 30 seconds of a new version reaching
  100% traffic may still execute on the previous version due to scheduler
  pre-fetching; build idempotency into every cron handler.

## Verification

```bash
# List live cron schedules for the worker
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/billing-worker/schedules" \
  | jq '.result.schedules'

# Confirm wrangler.toml matches after a deploy
npx wrangler deploy --env production --dry-run 2>&1 | grep -A10 "Cron Triggers"

# Run reconcile check manually
npx tsx scripts/reconcile-crons.ts
```

## Related

- `deploy/d1-schema-migration-sequencing-wrangler-remote.md`
- `deploy/workers-binding-version-management.md`
- `deploy/deployment-verification-smoke-tests.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/schedules/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
