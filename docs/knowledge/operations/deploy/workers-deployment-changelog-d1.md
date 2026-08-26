# Automated Deployment Changelog Tracking in D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your team deploys frequently to Cloudflare Workers and needs a durable, queryable record of every deployment: who deployed, which git SHA, to which environment, and what changed between deploys. GitHub Actions run logs expire; wrangler stdout is ephemeral. You need a persistent changelog stored in D1 so you can query deploy frequency, mean time between deploys, and diff history from a single API.

## Context

D1 is Cloudflare's edge SQL database, accessible from Workers without an egress hop. By recording a row on every successful `wrangler deploy`, the deployment changelog becomes part of the same infrastructure it describes — no external database, no third-party service. A lightweight Worker exposes a read API over the D1 table so dashboards and alerting pipelines can query deploy history in SQL.

The recording trigger is a GitHub Actions step that calls a secure internal Worker endpoint immediately after `wrangler deploy` succeeds.

## Solution

### Step 1 — D1 schema

```sql
-- migrations/0001_deploy_changelog.sql
CREATE TABLE IF NOT EXISTS deployments (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  service       TEXT    NOT NULL,
  environment   TEXT    NOT NULL,
  version       TEXT    NOT NULL,
  git_sha       TEXT    NOT NULL,
  git_ref       TEXT    NOT NULL,
  deployer      TEXT    NOT NULL,
  diff_summary  TEXT,
  deployed_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_deployments_service_env ON deployments (service, environment);
CREATE INDEX idx_deployments_deployed_at ON deployments (deployed_at);
```

Apply the migration:

```bash
npx wrangler d1 execute DEPLOY_LOG --file=migrations/0001_deploy_changelog.sql --env production
```

### Step 2 — Deploy recorder Worker

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  RECORD_SECRET: string; // set via wrangler secret
}

interface DeployPayload {
  service: string;
  environment: string;
  version: string;
  gitSha: string;
  gitRef: string;
  deployer: string;
  diffSummary?: string;
}

function unauthorized(): Response {
  return new Response('Unauthorized', { status: 401 });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Authenticate every request with a shared secret
    const providedSecret = request.headers.get('X-Deploy-Secret') ?? '';
    if (providedSecret !== env.RECORD_SECRET) return unauthorized();

    // POST /deploy — record a new deployment
    if (request.method === 'POST' && url.pathname === '/deploy') {
      const payload = await request.json<DeployPayload>();

      const stmt = env.DB.prepare(
        `INSERT INTO deployments (service, environment, version, git_sha, git_ref, deployer, diff_summary)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      );
      const result = await stmt
        .bind(
          payload.service,
          payload.environment,
          payload.version,
          payload.gitSha,
          payload.gitRef,
          payload.deployer,
          payload.diffSummary ?? null
        )
        .run();

      return Response.json({ id: result.meta.last_row_id, ok: true }, { status: 201 });
    }

    // GET /history?service=&env=&limit= — deployment history
    if (request.method === 'GET' && url.pathname === '/history') {
      const service = url.searchParams.get('service');
      const env_name = url.searchParams.get('env');
      const limit = Math.min(Number(url.searchParams.get('limit') ?? '20'), 100);

      const rows = await env.DB.prepare(
        `SELECT id, service, environment, version, git_sha, git_ref, deployer, diff_summary, deployed_at
         FROM deployments
         WHERE (? IS NULL OR service = ?)
           AND (? IS NULL OR environment = ?)
         ORDER BY deployed_at DESC
         LIMIT ?`
      )
        .bind(service, service, env_name, env_name, limit)
        .all();

      return Response.json(rows.results);
    }

    // GET /metrics?service=&env= — MTBD and deploy frequency
    if (request.method === 'GET' && url.pathname === '/metrics') {
      const service = url.searchParams.get('service');
      const env_name = url.searchParams.get('env');

      const row = await env.DB.prepare(
        `SELECT
           COUNT(*)                                           AS total_deploys,
           MIN(deployed_at)                                   AS first_deploy,
           MAX(deployed_at)                                   AS last_deploy,
           ROUND(
             (JULIANDAY(MAX(deployed_at)) - JULIANDAY(MIN(deployed_at)))
             / NULLIF(COUNT(*) - 1, 0) * 86400
           )                                                  AS avg_seconds_between_deploys
         FROM deployments
         WHERE (? IS NULL OR service = ?)
           AND (? IS NULL OR environment = ?)`
      )
        .bind(service, service, env_name, env_name)
        .first();

      return Response.json(row);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### Step 3 — GitHub Actions integration

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # needed for git diff

      - name: Install dependencies
        run: npm ci

      - name: Deploy Worker
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          OUTPUT=$(npx wrangler deploy --env production 2>&1)
          echo "$OUTPUT"
          VERSION=$(echo "$OUTPUT" | grep -oP '(?<=Current Version ID: )\S+')
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"

      - name: Generate diff summary
        id: diff
        run: |
          DIFF=$(git diff HEAD~1 HEAD --stat 2>/dev/null | tail -1)
          echo "summary=$DIFF" >> "$GITHUB_OUTPUT"

      - name: Record deployment in changelog
        env:
          DEPLOY_SECRET: ${{ secrets.DEPLOY_RECORD_SECRET }}
        run: |
          curl -fsSL -X POST https://deploy-log.orchords.workers.dev/deploy \
            -H "Content-Type: application/json" \
            -H "X-Deploy-Secret: $DEPLOY_SECRET" \
            -d "$(jq -n \
              --arg svc  "${{ github.repository }}" \
              --arg env  "production" \
              --arg ver  "${{ steps.deploy.outputs.version }}" \
              --arg sha  "${{ github.sha }}" \
              --arg ref  "${{ github.ref_name }}" \
              --arg who  "${{ github.actor }}" \
              --arg diff "${{ steps.diff.outputs.summary }}" \
              '{service:$svc,environment:$env,version:$ver,gitSha:$sha,gitRef:$ref,deployer:$who,diffSummary:$diff}')"
```

### Step 4 — Query examples

```bash
# Last 5 deploys for gateway-worker in production
curl -s "https://deploy-log.orchords.workers.dev/history?service=gateway-worker&env=production&limit=5" \
  -H "X-Deploy-Secret: $SECRET" | jq .

# Mean time between deploys
curl -s "https://deploy-log.orchords.workers.dev/metrics?service=gateway-worker&env=production" \
  -H "X-Deploy-Secret: $SECRET" | jq '.avg_seconds_between_deploys / 3600 | "\(.) hours"'
```

## Implementation Details

- D1 uses SQLite semantics. `JULIANDAY` arithmetic gives fractional day differences; multiplying by 86400 converts to seconds.
- `NULLIF(COUNT(*) - 1, 0)` prevents division by zero when there is only one deployment row.
- The `diff_summary` column stores a single-line `git diff --stat` summary, not a full patch, to stay within D1 row size limits (1 MB per row).
- The `version` field captures the Cloudflare deployment version ID printed by `wrangler deploy` (`Current Version ID: <id>`), enabling cross-referencing with the Cloudflare dashboard.
- The `X-Deploy-Secret` header is a simple shared secret suitable for internal tooling. For higher assurance, replace it with an asymmetric signature verified in the Worker.

## Anti-patterns

- **Recording the deploy before `wrangler deploy` succeeds.** A failed deploy recorded as successful creates phantom entries. Always record in a step that runs only after the deploy step exits 0.
- **Storing full git diffs in D1.** Large diffs approach the row size limit and bloat the database. Store only the `--stat` summary and link to the GitHub compare URL.
- **Exposing the history API without authentication.** Deployment history contains version IDs, deployer identities, and timing patterns useful to an attacker. Always require the shared secret.
- **Using `SELECT *` without a `LIMIT`.** A fast-moving project may accumulate thousands of rows; unbounded queries block the D1 worker thread.

## Gotchas

- D1 is eventually consistent in its replication. A read immediately after a write on a different PoP may return a slightly stale result. For the history API this is acceptable; do not use D1 as a real-time lock.
- Wrangler may print `Current Version ID` only when deploying to an account with Workers Versions enabled. Test the grep pattern in a staging run before relying on it in CI.
- GitHub Actions `github.sha` is the merge commit SHA on pull request merges, not the head commit of the feature branch. Log `github.event.pull_request.head.sha` if you need the PR head SHA.
- D1 free tier is 5 million row reads / month. A team deploying 50 times per day reads 1 500 rows/month in history queries — well within limits; metrics queries each read the full table, so add date filters for larger datasets.

## Verification

1. Trigger a manual deploy from GitHub Actions and confirm the workflow step `Record deployment in changelog` exits 0.
2. Query `/history?service=<your-service>&env=production&limit=1` and confirm the row matches the SHA and version from the deploy step output.
3. After at least two deploys, query `/metrics` and confirm `avg_seconds_between_deploys` is non-null.
4. Run `npx wrangler d1 execute DEPLOY_LOG --command "SELECT COUNT(*) FROM deployments" --env production` to verify rows are persisting.

## Related

- `workers-environment-promotion-pipeline.md`
- `rollback-wrangler-versions.md`
- `workers-deployment-verification-smoke-tests.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
