# GitHub Actions Scheduled Cron Workflows for Cloudflare Workers Maintenance

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cloudflare Workers infrastructure accumulates stale state over time: expired KV keys that were never cleaned up,
D1 databases that need periodic `VACUUM` or `ANALYZE`, R2 lifecycle-delete jobs for old preview artifacts, and
Durable Object alarms that need resetting after crashes. None of these are triggered by deploys. You need
GitHub Actions `schedule` workflows to run maintenance routines on a cron cadence without manual intervention.

## Context

GitHub Actions supports `on.schedule` with standard POSIX cron syntax (UTC). Scheduled workflows run on the
default branch only and do not inherit branch-level environment secrets unless the environment is explicitly
referenced. Cloudflare provides the Wrangler CLI and REST API for most administrative operations; combining them
with the `schedule` trigger creates a lightweight maintenance plane without extra infrastructure.

---

## Workflow Skeleton: Weekly D1 VACUUM

D1 SQLite databases accumulate fragmentation after high-insert workloads. A weekly `VACUUM` reclaims space and
improves query performance.

```yaml
# .github/workflows/maintenance-d1-vacuum.yml
name: Maintenance — D1 VACUUM

on:
  schedule:
    - cron: "0 3 * * 0"   # 03:00 UTC every Sunday
  workflow_dispatch:        # allow manual trigger during incidents

jobs:
  vacuum:
    runs-on: ubuntu-24.04
    environment: production  # pulls Cloudflare secrets from env protection

    steps:
      - uses: actions/checkout@v4

      - name: Install Wrangler
        run: npm install -g wrangler@latest

      - name: VACUUM production D1
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: |
          wrangler d1 execute DB \
            --remote \
            --command "VACUUM;" \
            --env production
```

---

## Purging Stale KV Keys via Workers Script

Cloudflare KV does not support server-side TTL queries, but a Worker can iterate metadata to identify and delete
keys that exceed a logical expiry stored in the value.

```typescript
// src/maintenance/kv-purge.ts
export interface Env {
  CACHE_KV: KVNamespace;
}

export default {
  // Called by a scheduled GitHub Actions workflow via the REST dispatch API
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.headers.get("X-Maintenance-Key") !== "INTERNAL") {
      return new Response("Forbidden", { status: 403 });
    }

    let cursor: string | undefined;
    let deleted = 0;
    const now = Date.now();

    do {
      const page = await env.CACHE_KV.list({ cursor, limit: 1000 });

      for (const key of page.keys) {
        const meta = key.metadata as { expiresAt?: number } | undefined;
        if (meta?.expiresAt && meta.expiresAt < now) {
          await env.CACHE_KV.delete(key.name);
          deleted++;
        }
      }

      cursor = page.list_complete ? undefined : (page as any).cursor;
    } while (cursor);

    return new Response(JSON.stringify({ deleted }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

```yaml
# .github/workflows/maintenance-kv-purge.yml
name: Maintenance — KV Stale Key Purge

on:
  schedule:
    - cron: "30 2 * * *"   # 02:30 UTC nightly

jobs:
  purge:
    runs-on: ubuntu-24.04
    steps:
      - name: Invoke maintenance endpoint
        env:
          WORKER_URL: ${{ secrets.WORKER_MAINTENANCE_URL }}
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "X-Maintenance-Key: INTERNAL" \
            "$WORKER_URL/kv-purge")
          echo "Response: $STATUS"
          [ "$STATUS" = "200" ] || exit 1
```

---

## R2 Lifecycle: Deleting Old Preview Artifacts

Preview-deploy artifacts accumulate in R2 buckets. A scheduled workflow lists objects with a `preview/` prefix
older than 30 days and removes them using the Cloudflare REST API.

```typescript
// scripts/r2-lifecycle-delete.ts  (runs in Node via tsx in the workflow)
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const BUCKET = process.env.R2_BUCKET_NAME!;
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1_000;

async function listObjects(cursor?: string): Promise<{ objects: any[]; cursor?: string }> {
  const url = new URL(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET}/objects`,
  );
  url.searchParams.set("prefix", "preview/");
  if (cursor) url.searchParams.set("cursor", cursor);

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${API_TOKEN}` },
  });
  const json: any = await res.json();
  return { objects: json.result.objects, cursor: json.result.truncated ? json.result.cursor : undefined };
}

async function main() {
  const cutoff = Date.now() - MAX_AGE_MS;
  let cursor: string | undefined;
  let total = 0;

  do {
    const { objects, cursor: next } = await listObjects(cursor);
    for (const obj of objects) {
      if (new Date(obj.uploaded).getTime() < cutoff) {
        await fetch(
          `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET}/objects/${obj.key}`,
          { method: "DELETE", headers: { Authorization: `Bearer ${API_TOKEN}` } },
        );
        total++;
      }
    }
    cursor = next;
  } while (cursor);

  console.log(`Deleted ${total} preview objects`);
}

main();
```

```yaml
# .github/workflows/maintenance-r2-lifecycle.yml
name: Maintenance — R2 Preview Cleanup

on:
  schedule:
    - cron: "0 1 * * 1"   # 01:00 UTC every Monday

jobs:
  cleanup:
    runs-on: ubuntu-24.04
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm ci
      - name: Run R2 lifecycle delete
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          R2_BUCKET_NAME: ${{ vars.R2_PREVIEW_BUCKET }}
        run: npx tsx scripts/r2-lifecycle-delete.ts
```

---

## Posting Maintenance Results to Job Summary

Use GitHub's step summary to produce a human-readable report visible in the Actions UI without needing a
separate notification channel.

```yaml
      - name: Write maintenance summary
        if: always()
        run: |
          cat >> "$GITHUB_STEP_SUMMARY" <<'EOF'
          ## Maintenance Run — $(date -u +%Y-%m-%d)

          | Task | Status |
          |------|--------|
          | D1 VACUUM | ${{ steps.vacuum.outcome }} |
          | KV purge  | ${{ steps.purge.outcome }} |
          | R2 cleanup | ${{ steps.cleanup.outcome }} |
          EOF
```

---

## Anti-patterns

- **Running maintenance in deploy workflows** — coupling maintenance to deploys means it runs too frequently
  on high-deploy repos and blocks deployments if the maintenance step fails. Keep them separate scheduled workflows.
- **No `workflow_dispatch` fallback** — scheduled workflows cannot be triggered from the GitHub UI without it.
  Always add `workflow_dispatch:` alongside `schedule:` for manual recovery runs.
- **Hardcoding cron times that collide with peak traffic** — schedule maintenance during known low-traffic
  windows; for global apps avoid UTC 08:00–18:00 (overlap with EU/US business hours).
- **Not reporting failures** — scheduled jobs that silently fail go unnoticed for days. Add `if: failure()`
  steps that send Slack/PagerDuty alerts or open GitHub issues automatically.

---

## Gotchas

- GitHub disables scheduled workflows after **60 days of repository inactivity**. Re-enable them by pushing a
  commit or manually triggering a run.
- `on.schedule` runs only on the **default branch**. Maintenance workflows on feature branches are ignored.
- Wrangler `--remote` D1 commands consume D1 read/write billing units even during maintenance; large `VACUUM`
  on busy databases may consume significant write units.
- The GitHub Actions scheduler has a jitter of up to 15 minutes for scheduled workflows; do not rely on exact
  fire times for SLA-sensitive operations.

---

## Verification

```bash
# Manually trigger and watch logs
gh workflow run maintenance-d1-vacuum.yml --ref main
gh run watch $(gh run list --workflow=maintenance-d1-vacuum.yml -L 1 --json databaseId -q '.[0].databaseId')

# Confirm D1 page count decreased after VACUUM
wrangler d1 execute DB --remote --command "PRAGMA page_count; PRAGMA freelist_count;" --env production
```

---

## Related

- `github-actions-cloudflare-d1-migration-pipeline.md`
- `github-actions-d1-snapshot-artifacts.md`
- `github-actions-release-asset-r2-distribution.md`
- `github-actions-workflow-dispatch.md`

---

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule
- https://developers.cloudflare.com/d1/reference/database-commands/#vacuum
- https://developers.cloudflare.com/kv/api/list-keys/
- https://developers.cloudflare.com/r2/api/s3/api/#listobjectsv2
